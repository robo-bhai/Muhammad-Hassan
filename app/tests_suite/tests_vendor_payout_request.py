"""
Tests: vendor payout request (vendor raqam maange -> admin Paid / Reject).

Run:  python manage.py test app.tests_suite.tests_vendor_payout_request -v 2

NOTE: written by reading the code, without a Django project to run it in. If a fixture line fails on
a field name, fix it in setUp - the assertions are what matter. The sales/COD hold maths is patched
(`_vendor_share`, `_cash_hold`, `vendor_earnings`) so the tests do not need a full invoice fixture.

Hand-calculated numbers (balance 5000, nothing held, minimum 500):
    withdrawable                      -> 5000.00
    balance 5000, recent hold 1200, rider cash hold 800, pending 0   -> 3000.00
    same but pending request 1000                                   -> 2000.00
    holds bigger than balance                                       -> 0.00 (never negative)
    request 499.99 (below minimum)    -> PayoutError
    request 5000.01 (above available) -> PayoutError
    second request while one pending  -> PayoutError (and DB allows only one pending)
    mark_paid                         -> VendorPayout(amount == request amount), status 'paid'
    mark_paid twice                   -> PayoutError, still one VendorPayout
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from app.customer import payout_requests as pr
from app.models import Vendor, VendorPayout, VendorPayoutRequest, VendorProfile

D = Decimal
EARN = 'app.customer.vendor_commission.vendor_earnings'
SHARE = 'app.customer.payout_requests._vendor_share'
CASH = 'app.customer.payout_requests._cash_hold'
SETTINGS = 'app.customer.payout_requests.payout_settings'


def earnings(balance):
    return {'units': 1, 'sales': D(balance), 'commission': D('0'), 'payable': D(balance),
            'paid': D('0'), 'balance': D(balance)}


class PayoutBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('vend', 'v@x.com', 'pw12345!')
        self.vendor = Vendor.objects.create(name='Pizza Hub')
        self.profile = VendorProfile.objects.create(
            vendor=self.vendor, user=self.user, business_name='Pizza Hub', is_approved=True,
            payout_method='bank', payout_account_title='Pizza Hub Ltd', payout_account_no='PK36SCBL0000001123456702')
        self.admin = User.objects.create_superuser('boss', 'b@x.com', 'x')
        self.cfg = {'min_amount': D('500'), 'hold_days': 2}
        patches = [mock.patch(SETTINGS, return_value=self.cfg), mock.patch(SHARE, return_value=D('0.00')),
                   mock.patch(CASH, return_value=D('0.00')), mock.patch(EARN, return_value=earnings('5000'))]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.m_share, self.m_cash, self.m_earn = self.mocks[1], self.mocks[2], self.mocks[3]


class WithdrawableTests(PayoutBase):
    def test_nothing_held(self):
        self.assertEqual(pr.withdrawable(self.vendor)['available'], D('5000.00'))

    def test_recent_and_cash_holds_subtract(self):
        self.m_share.return_value = D('1200.00')
        self.m_cash.return_value = D('800.00')
        self.assertEqual(pr.withdrawable(self.vendor)['available'], D('3000.00'))

    def test_pending_request_is_reserved(self):
        VendorPayoutRequest.objects.create(vendor=self.vendor, amount=D('1000'), status='pending')
        w = pr.withdrawable(self.vendor)
        self.assertEqual(w['pending'], D('1000.00'))
        self.assertEqual(w['available'], D('4000.00'))

    def test_never_negative(self):
        self.m_share.return_value = D('9000.00')
        self.assertEqual(pr.withdrawable(self.vendor)['available'], D('0.00'))

    def test_hold_days_zero_skips_recent_hold(self):
        self.cfg['hold_days'] = 0
        self.m_share.return_value = D('1200.00')
        self.assertEqual(pr.withdrawable(self.vendor)['available'], D('5000.00'))
        self.m_share.assert_not_called()


class CreateRequestTests(PayoutBase):
    def test_valid_request(self):
        req = pr.create_request(self.profile, '1500', 'Eid se pehle')
        self.assertEqual(req.amount, D('1500.00'))
        self.assertEqual(req.status, 'pending')
        self.assertEqual(req.account_no, 'PK36SCBL0000001123456702')

    def test_exact_available_ok_and_one_paisa_more_rejected(self):
        with self.assertRaises(pr.PayoutError):
            pr.create_request(self.profile, '5000.01')
        self.assertEqual(pr.create_request(self.profile, '5000.00').amount, D('5000.00'))

    def test_below_minimum_rejected(self):
        with self.assertRaises(pr.PayoutError):
            pr.create_request(self.profile, '499.99')

    def test_bad_amounts_rejected(self):
        for bad in ('', 'abc', '0', '-5', '1e999999'):
            with self.assertRaises(pr.PayoutError, msg=bad):
                pr.create_request(self.profile, bad)
        self.assertEqual(VendorPayoutRequest.objects.count(), 0)

    def test_only_one_pending(self):
        pr.create_request(self.profile, '1000')
        with self.assertRaises(pr.PayoutError):
            pr.create_request(self.profile, '1000')
        self.assertEqual(VendorPayoutRequest.objects.filter(status='pending').count(), 1)

    def test_database_blocks_second_pending(self):
        VendorPayoutRequest.objects.create(vendor=self.vendor, amount=D('600'), status='pending')
        with self.assertRaises(IntegrityError), transaction.atomic():
            VendorPayoutRequest.objects.create(vendor=self.vendor, amount=D('700'), status='pending')

    def test_unapproved_vendor_or_missing_account_rejected(self):
        VendorProfile.objects.filter(pk=self.profile.pk).update(is_approved=False)
        with self.assertRaises(pr.PayoutError):
            pr.create_request(self.profile, '1000')
        VendorProfile.objects.filter(pk=self.profile.pk).update(is_approved=True, payout_account_no='')
        with self.assertRaises(pr.PayoutError):
            pr.create_request(self.profile, '1000')

    def test_cancel_then_new_request_allowed(self):
        req = pr.create_request(self.profile, '1000')
        pr.cancel_request(self.profile, req.pk)
        req.refresh_from_db()
        self.assertEqual(req.status, 'cancelled')
        self.assertEqual(pr.create_request(self.profile, '1000').status, 'pending')

    def test_cannot_cancel_someone_elses_request(self):
        other_vendor = Vendor.objects.create(name='Other')
        other = VendorPayoutRequest.objects.create(vendor=other_vendor, amount=D('600'))
        with self.assertRaises(pr.PayoutError):
            pr.cancel_request(self.profile, other.pk)
        other.refresh_from_db()
        self.assertEqual(other.status, 'pending')


class AccountTests(PayoutBase):
    def test_bank_iban_cleaned(self):
        self.assertEqual(pr.clean_account_no('bank', 'pk36 scbl-0000 0011 2345 6702'), 'PK36SCBL0000001123456702')

    def test_mobile_wallet_needs_number(self):
        self.assertEqual(pr.clean_account_no('jazzcash', '0300-1234567'), '03001234567')
        with self.assertRaises(pr.PayoutError):
            pr.clean_account_no('easypaisa', 'abc123')

    def test_bad_bank_number_rejected(self):
        with self.assertRaises(pr.PayoutError):
            pr.clean_account_no('bank', '12')

    def test_save_account_validates_method_and_title(self):
        with self.assertRaises(pr.PayoutError):
            pr.save_account(self.profile, 'cash', 'Ali Khan', '03001234567')
        with self.assertRaises(pr.PayoutError):
            pr.save_account(self.profile, 'jazzcash', ' ', '03001234567')
        pr.save_account(self.profile, 'jazzcash', 'Ali  Khan', '0300 1234567')
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.payout_method, self.profile.payout_account_title,
                          self.profile.payout_account_no), ('jazzcash', 'Ali Khan', '03001234567'))


class AdminDecisionTests(PayoutBase):
    def setUp(self):
        super().setUp()
        self.req = pr.create_request(self.profile, '2000')

    def test_mark_paid_creates_payout(self):
        pr.mark_paid(self.req.pk, self.admin, 'TXN-123')
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'paid')
        self.assertEqual(self.req.reviewed_by_id, self.admin.id)
        payout = VendorPayout.objects.get()
        self.assertEqual(payout.amount, D('2000.00'))
        self.assertEqual(payout.reference_no, 'TXN-123')
        self.assertEqual(payout.method, 'bank')
        self.assertEqual(self.req.payout_id, payout.pk)

    def test_mark_paid_needs_reference(self):
        with self.assertRaises(pr.PayoutError):
            pr.mark_paid(self.req.pk, self.admin, '  ')
        self.assertEqual(VendorPayout.objects.count(), 0)

    def test_mark_paid_twice_pays_once(self):
        pr.mark_paid(self.req.pk, self.admin, 'TXN-1')
        with self.assertRaises(pr.PayoutError):
            pr.mark_paid(self.req.pk, self.admin, 'TXN-2')
        self.assertEqual(VendorPayout.objects.count(), 1)

    def test_mark_paid_refused_when_balance_dropped(self):
        self.m_earn.return_value = earnings('1999.99')
        with self.assertRaises(pr.PayoutError):
            pr.mark_paid(self.req.pk, self.admin, 'TXN-1')
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'pending')
        self.assertEqual(VendorPayout.objects.count(), 0)

    def test_reject_needs_reason_and_frees_the_vendor(self):
        with self.assertRaises(pr.PayoutError):
            pr.reject(self.req.pk, self.admin, '')
        pr.reject(self.req.pk, self.admin, 'Account number galat')
        self.req.refresh_from_db()
        self.assertEqual((self.req.status, self.req.reject_reason), ('rejected', 'Account number galat'))
        self.assertEqual(pr.create_request(self.profile, '1000').status, 'pending')

    def test_cannot_reject_a_paid_request(self):
        pr.mark_paid(self.req.pk, self.admin, 'TXN-1')
        with self.assertRaises(pr.PayoutError):
            pr.reject(self.req.pk, self.admin, 'oops')

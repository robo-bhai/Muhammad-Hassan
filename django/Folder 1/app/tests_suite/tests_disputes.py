"""
Tests: order disputes (customer report -> admin wallet refund / reject).

Run:  python manage.py test app.tests_suite.tests_disputes -v 2

NOTE: written by reading the code, without a Django project to run it in. If a fixture line fails on
a field name, fix it in setUp - the assertions are what matter.

Hand-calculated numbers (order total patched to 500.00):
    full refund                 -> wallet +500.00
    partial 120.50              -> wallet +120.50
    partial 500.01 / 0 / -5     -> rejected with DisputeError, wallet unchanged
    second refund on same order -> DisputeError, wallet still +500.00
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from app.customer import disputes as logic
from app.customer import offers
from app.models import Customer, OrderDispute, SaleOrder, WalletTransaction, Warehouse

D = Decimal
TOTAL = 'app.customer.disputes.store_orders.order_payable_total'


class DisputeBase(TestCase):
    def setUp(self):
        self.cust = Customer.objects.create(name='Ali', customer_code='C-001')
        self.wh = Warehouse.objects.create(name='Main')
        self.admin = User.objects.create_superuser('boss', 'b@x.com', 'x')
        self.order = self._order('SO-1')

    def _order(self, no, status='delivered'):
        return SaleOrder.objects.create(order_no=no, customer=self.cust, warehouse=self.wh,
                                        order_date=timezone.now(), status=status)

    def balance(self):
        return offers.wallet_balance(self.cust)


class OpenDisputeTests(DisputeBase):
    def test_delivered_order_can_open(self):
        d = logic.open_dispute(self.order, 'missing_item', 'Fries missing')
        self.assertEqual(d.status, 'open')
        self.assertEqual(d.customer_id, self.cust.id)

    def test_invoiced_counts_as_delivered(self):
        o = self._order('SO-2', status='invoiced')
        self.assertTrue(logic.can_open_dispute(o)[0])

    def test_not_delivered_or_cancelled_rejected(self):
        for st in ('pending', 'processing', 'cancelled'):
            o = self._order(f'SO-{st}', status=st)
            self.assertFalse(logic.can_open_dispute(o)[0], st)

    def test_one_dispute_per_order(self):
        logic.open_dispute(self.order, 'late')
        order = SaleOrder.objects.get(pk=self.order.pk)
        with self.assertRaises(logic.DisputeError):
            logic.open_dispute(order, 'wrong_item')

    def test_window_expires(self):
        SaleOrder.objects.filter(pk=self.order.pk).update(updated_at=timezone.now() - timedelta(hours=49))
        order = SaleOrder.objects.get(pk=self.order.pk)
        ok, why = logic.can_open_dispute(order)
        self.assertFalse(ok)
        self.assertIn('ghante', why)

    def test_other_reason_needs_description_and_bad_reason_rejected(self):
        with self.assertRaises(logic.DisputeError):
            logic.open_dispute(self.order, 'other', '  ')
        with self.assertRaises(logic.DisputeError):
            logic.open_dispute(self.order, 'made_up_reason')


class ResolveDisputeTests(DisputeBase):
    def setUp(self):
        super().setUp()
        self.d = logic.open_dispute(self.order, 'bad_quality', 'Cold food')

    @mock.patch(TOTAL, return_value=D('500.00'))
    def test_full_refund_credits_wallet(self, _):
        logic.resolve_dispute(self.d, 'refund_full', self.admin, note='Sorry')
        self.d.refresh_from_db()
        self.assertEqual(self.d.status, 'resolved')
        self.assertEqual(self.d.refund_amount, D('500.00'))
        self.assertEqual(self.balance(), D('500.00'))
        self.assertEqual(WalletTransaction.objects.filter(order=self.order, kind='dispute').count(), 1)

    @mock.patch(TOTAL, return_value=D('500.00'))
    def test_partial_refund(self, _):
        logic.resolve_dispute(self.d, 'refund_partial', self.admin, amount='120.50')
        self.assertEqual(self.balance(), D('120.50'))

    @mock.patch(TOTAL, return_value=D('500.00'))
    def test_partial_amount_limits(self, _):
        for bad in ('500.01', '0', '-5', 'abc', None):
            with self.assertRaises(logic.DisputeError, msg=str(bad)):
                logic.resolve_dispute(self.d, 'refund_partial', self.admin, amount=bad)
        self.assertEqual(self.balance(), D('0.00'))
        self.d.refresh_from_db()
        self.assertEqual(self.d.status, 'open')

    @mock.patch(TOTAL, return_value=D('500.00'))
    def test_cannot_resolve_twice_or_refund_twice(self, _):
        logic.resolve_dispute(self.d, 'refund_full', self.admin)
        with self.assertRaises(logic.DisputeError):
            logic.resolve_dispute(self.d, 'refund_full', self.admin)
        self.assertEqual(self.balance(), D('500.00'))

    @mock.patch(TOTAL, return_value=D('500.00'))
    def test_reject_needs_reason_and_pays_nothing(self, _):
        with self.assertRaises(logic.DisputeError):
            logic.resolve_dispute(self.d, 'reject', self.admin, note='')
        logic.resolve_dispute(self.d, 'reject', self.admin, note='Photo shows item was delivered')
        self.d.refresh_from_db()
        self.assertEqual((self.d.status, self.d.resolution), ('rejected', 'no_refund'))
        self.assertEqual(self.balance(), D('0.00'))

    @mock.patch(TOTAL, return_value=D('500.00'))
    def test_review_then_resolve(self, _):
        logic.mark_under_review(self.d, self.admin)
        self.d.refresh_from_db()
        self.assertEqual(self.d.status, 'under_review')
        logic.resolve_dispute(self.d, 'refund_full', self.admin)
        self.d.refresh_from_db()
        self.assertEqual(self.d.status, 'resolved')

    def test_unknown_action(self):
        with self.assertRaises(logic.DisputeError):
            logic.resolve_dispute(self.d, 'delete_everything', self.admin)


class ResponseTests(DisputeBase):
    """Vendor / rider ka jawab: ek dafa, sirf open dispute par, sirf apne dispute par."""

    def setUp(self):
        super().setUp()
        from app.models import RiderProfile, Vendor
        self.vendor = Vendor.objects.create(name='Store A', vendor_code='V-001')
        self.other_vendor = Vendor.objects.create(name='Store B', vendor_code='V-002')
        ru = User.objects.create_user('rider1', password='x')
        self.rider = RiderProfile.objects.create(user=ru, name='Bilal', phone='03000000001')
        self.d = logic.open_dispute(self.order, 'missing_item', 'Fries missing')
        OrderDispute.objects.filter(pk=self.d.pk).update(vendor=self.vendor, rider=self.rider)
        self.d.refresh_from_db()

    def test_vendor_and_rider_can_respond_once(self):
        logic.submit_response(self.d, 'vendor', 'Packed correctly')
        logic.submit_response(self.d, 'rider', 'Handed over sealed bag')
        self.d.refresh_from_db()
        self.assertEqual(self.d.vendor_response, 'Packed correctly')
        self.assertEqual(self.d.rider_response, 'Handed over sealed bag')
        self.assertIsNotNone(self.d.vendor_responded_at)
        with self.assertRaises(logic.DisputeError):
            logic.submit_response(self.d, 'vendor', 'Changed my mind')

    def test_empty_or_too_long_response_rejected(self):
        with self.assertRaises(logic.DisputeError):
            logic.submit_response(self.d, 'vendor', '   ')
        with self.assertRaises(logic.DisputeError):
            logic.submit_response(self.d, 'vendor', 'x' * (logic.RESPONSE_MAX_CHARS + 1))

    @mock.patch(TOTAL, return_value=D('500.00'))
    def test_no_response_after_resolution(self, _):
        logic.resolve_dispute(self.d, 'reject', self.admin, note='Evidence shows delivered')
        with self.assertRaises(logic.DisputeError):
            logic.submit_response(self.d, 'rider', 'Too late')

    def test_scope_and_pending_count(self):
        self.assertEqual(list(logic.disputes_for('vendor', self.vendor)), [self.d])
        self.assertEqual(logic.disputes_for('vendor', self.other_vendor).count(), 0)
        self.assertEqual(logic.disputes_for('rider', self.rider).count(), 1)
        self.assertEqual(logic.needs_response_count('vendor', self.vendor), 1)
        logic.submit_response(self.d, 'vendor', 'Packed correctly')
        self.assertEqual(logic.needs_response_count('vendor', self.vendor), 0)
        self.assertEqual(logic.needs_response_count('rider', self.rider), 1)

    def test_short_name_hides_surname(self):
        c = Customer(name='Hadi Ahmed Khan')
        self.assertEqual(logic.short_name(c), 'Hadi K.')
        self.assertEqual(logic.short_name(Customer(name='Sara')), 'Sara')

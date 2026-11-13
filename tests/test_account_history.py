"""
Django tests: suspend / approve / blacklist history page.

Copy this file to app/tests_account_history.py and run:
    python manage.py migrate
    python manage.py test app.tests_account_history

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models, fix that line in setUp (the assertions themselves are the important part).
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.models import AccountActionLog, Customer, CustomerProfile, Vendor, VendorProfile


class AccountHistoryTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.client.force_login(self.admin)
        self.customer = Customer.objects.create(name='Ali', contact_number='0300-1234567')
        self.cuser = User.objects.create_user('cust_ali', 'ali@example.com', 'secret12')
        self.profile = CustomerProfile.objects.create(customer=self.customer, user=self.cuser)

    def _cust(self, action, **extra):
        return self.client.post(reverse('customer_suspend_action', args=[self.customer.pk, action]), extra)

    def test_customer_suspend_and_unsuspend_are_logged(self):
        self._cust('suspend', reason='Fake orders')
        self._cust('unsuspend')
        rows = list(AccountActionLog.objects.filter(kind='customer').order_by('id'))
        self.assertEqual([r.action for r in rows], ['suspend', 'unsuspend'])
        self.assertEqual(rows[0].reason, 'Fake orders')
        self.assertEqual(rows[0].by, self.admin)
        self.assertEqual(rows[0].by_name, 'boss')
        self.assertEqual(rows[0].name, 'Ali')
        self.assertEqual(rows[0].ref_id, self.customer.pk)

    def test_blacklist_choice_is_in_detail(self):
        self._cust('suspend', reason='x', blacklist='1', blacklist_device='1')
        self.assertIn('device', AccountActionLog.objects.get(action='suspend').detail)

    def test_vendor_suspend_and_approve_are_logged(self):
        vendor = Vendor.objects.create(name='Khan Traders', contact_number='0321-7654321')
        vuser = User.objects.create_user('vendor_1', 'v@example.com', 'secret12')
        vp = VendorProfile.objects.create(vendor=vendor, user=vuser, business_name='Khan Traders', is_approved=True)
        self.client.post(reverse('vendor_account_action', args=[vp.pk, 'suspend']), {'reason': 'Fake products'})
        self.client.post(reverse('vendor_account_action', args=[vp.pk, 'approve']))
        rows = list(AccountActionLog.objects.filter(kind='vendor').order_by('id'))
        self.assertEqual([r.action for r in rows], ['suspend', 'approve'])
        self.assertEqual(rows[0].reason, 'Fake products')
        self.assertEqual(rows[0].ref_id, vendor.pk)

    def test_manual_blacklist_is_logged(self):
        self.client.post(reverse('blocked_add'), {'kind': 'phone', 'value': '03001234567', 'reason': 'spam'})
        r = AccountActionLog.objects.get(action='block')
        self.assertEqual((r.kind, r.reason, r.detail), ('other', 'spam', 'phone'))

    def test_history_survives_user_delete(self):
        self._cust('suspend', reason='x')
        self.admin.delete()
        r = AccountActionLog.objects.get()
        self.assertIsNone(r.by)
        self.assertEqual(r.by_name, 'boss')

    def test_page_filters_and_csv(self):
        self._cust('suspend', reason='Fake orders')
        self._cust('unsuspend')
        r = self.client.get(reverse('account_history') + '?action=suspend')
        self.assertContains(r, 'Fake orders')
        self.assertNotContains(r, 'Unsuspend</span>')
        r = self.client.get(reverse('account_history') + '?search=boss')
        self.assertContains(r, 'Ali')
        r = self.client.get(reverse('account_history') + '?export=csv')
        self.assertEqual(r['Content-Type'].split(';')[0], 'text/csv')
        self.assertIn('Fake orders', r.content.decode('utf-8'))

    def test_bad_date_filter_does_not_crash(self):
        r = self.client.get(reverse('account_history') + '?from=garbage&to=2026-99-99')
        self.assertEqual(r.status_code, 200)

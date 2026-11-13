"""
Django tests: blacklist (blocked phone / email / device).

Copy this file to app/tests_blacklist.py and run:
    python manage.py migrate
    python manage.py test app.tests_blacklist

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models, fix that line in setUp (the assertions themselves are the important part).
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.models import BlockedIdentity, Customer, CustomerProfile, Vendor, VendorProfile
from app.utils.blacklist import block_account, blocked_identity, unblock_ref


class BlacklistHelperTests(TestCase):
    def test_phone_blocked_in_any_format(self):
        block_account(phones=['0300-1234567'], reason='fraud', source_ref='customer:1')
        for raw in ['03001234567', '+92 300 1234567', '923001234567']:
            self.assertIsNotNone(blocked_identity(phone=raw), raw)
        self.assertIsNone(blocked_identity(phone='03111234567'))

    def test_email_blocked_ignoring_case(self):
        block_account(emails=['Bad@Example.com'])
        self.assertIsNotNone(blocked_identity(email='bad@example.COM'))
        self.assertIsNone(blocked_identity(email='good@example.com'))

    def test_device_only_when_given(self):
        block_account(device='abc123')
        self.assertIsNotNone(blocked_identity(device='abc123'))
        self.assertIsNone(blocked_identity(device='other'))
        self.assertIsNone(blocked_identity())

    def test_bad_values_are_ignored(self):
        self.assertEqual(block_account(phones=['123', ''], emails=['no-at-sign']), 0)
        self.assertEqual(BlockedIdentity.objects.count(), 0)

    def test_unblock_ref_removes_only_that_account(self):
        block_account(phones=['03001234567'], source_ref='customer:1')
        block_account(phones=['03211234567'], source_ref='customer:2')
        unblock_ref('customer:1')
        self.assertIsNone(blocked_identity(phone='03001234567'))
        self.assertIsNotNone(blocked_identity(phone='03211234567'))

    def test_blocking_twice_does_not_duplicate(self):
        block_account(phones=['03001234567'])
        block_account(phones=['+923001234567'])
        self.assertEqual(BlockedIdentity.objects.count(), 1)


class SuspendWithBlacklistTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.customer = Customer.objects.create(name='Ali', contact_number='0300-1234567', email='ali@example.com')
        self.user = User.objects.create_user('cust_ali', 'ali2@example.com', 'secret12')
        self.profile = CustomerProfile.objects.create(customer=self.customer, user=self.user,
                                                      signup_device='dev-1')
        self.client.force_login(self.admin)

    def _suspend(self, **extra):
        data = {'reason': 'Fraud'}
        data.update(extra)
        return self.client.post(reverse('customer_suspend_action', args=[self.customer.pk, 'suspend']), data)

    def test_suspend_without_blacklist_blocks_nothing(self):
        self._suspend()
        self.assertEqual(BlockedIdentity.objects.count(), 0)

    def test_suspend_with_blacklist_blocks_phone_and_both_emails_not_device(self):
        self._suspend(blacklist='1')
        self.assertIsNotNone(blocked_identity(phone='+923001234567'))
        self.assertIsNotNone(blocked_identity(email='ali@example.com'))
        self.assertIsNotNone(blocked_identity(email='ali2@example.com'))
        self.assertIsNone(blocked_identity(device='dev-1'))

    def test_device_only_when_asked(self):
        self._suspend(blacklist='1', blacklist_device='1')
        self.assertIsNotNone(blocked_identity(device='dev-1'))

    def test_unsuspend_clears_blacklist(self):
        self._suspend(blacklist='1', blacklist_device='1')
        self.client.post(reverse('customer_suspend_action', args=[self.customer.pk, 'unsuspend']))
        self.assertEqual(BlockedIdentity.objects.count(), 0)

    def test_blocked_phone_cannot_register_in_shop(self):
        self._suspend(blacklist='1')
        self.client.logout()
        before = User.objects.count()
        self.client.post(reverse('customer_register'), {
            'full_name': 'Ali New', 'phone': '03001234567', 'email': 'brandnew@example.com',
            'city': 'Lahore', 'address': 'House 1, Street 2, Lahore',
            'password': 'Secret#12345', 'confirm_password': 'Secret#12345'})
        self.assertEqual(User.objects.count(), before)

    def test_vendor_suspend_with_blacklist_blocks_new_registration(self):
        vendor = Vendor.objects.create(name='Khan Traders', contact_number='0321-7654321')
        vuser = User.objects.create_user('vendor_1', 'vendor@example.com', 'secret12')
        vp = VendorProfile.objects.create(vendor=vendor, user=vuser, business_name='Khan Traders',
                                          is_approved=True)
        self.client.post(reverse('vendor_account_action', args=[vp.pk, 'suspend']),
                         {'reason': 'Fake products', 'blacklist': '1'})
        self.assertIsNotNone(blocked_identity(phone='03217654321'))
        self.assertIsNotNone(blocked_identity(email='vendor@example.com'))
        # dobara approve -> blacklist hat jati hai
        self.client.post(reverse('vendor_account_action', args=[vp.pk, 'approve']))
        self.assertEqual(BlockedIdentity.objects.count(), 0)


class BlacklistPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.client.force_login(self.admin)

    def test_add_list_remove(self):
        self.client.post(reverse('blocked_add'), {'kind': 'phone', 'value': '0300 1234567', 'reason': 'test'})
        r = self.client.get(reverse('blocked_list'))
        self.assertContains(r, '0300 1234567')
        entry = BlockedIdentity.objects.get()
        self.client.post(reverse('blocked_remove', args=[entry.pk]))
        self.assertEqual(BlockedIdentity.objects.count(), 0)

    def test_device_cannot_be_added_by_hand(self):
        self.client.post(reverse('blocked_add'), {'kind': 'device', 'value': 'abc'})
        self.assertEqual(BlockedIdentity.objects.count(), 0)

    def test_get_request_does_not_remove(self):
        e = BlockedIdentity.objects.create(kind='email', value='a@b.com', label='a@b.com')
        r = self.client.get(reverse('blocked_remove', args=[e.pk]))
        self.assertEqual(r.status_code, 405)
        self.assertEqual(BlockedIdentity.objects.count(), 1)

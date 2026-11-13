"""
Django tests: duplicate customer / vendor control.

Copy this file to app/tests_duplicate_control.py and run:
    python manage.py test app.tests_duplicate_control

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models, fix that line in setUp (the assertions themselves are the important part).
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.models import Customer, Vendor


class CustomerDuplicateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.client.force_login(self.admin)
        self.first = Customer.objects.create(name='Ali', contact_number='0300-1234567')

    def _create(self, **kw):
        data = {'name': 'Bilal', 'contact_number': '+92 300 1234567'}
        data.update(kw)
        return self.client.post(reverse('customer_create'), data)

    def test_same_number_in_other_format_is_blocked(self):
        self._create()
        self.assertEqual(Customer.objects.filter(name='Bilal').count(), 0)

    def test_allow_duplicate_phone_checkbox_overrides(self):
        self._create(allow_duplicate_phone='1')
        self.assertEqual(Customer.objects.filter(name='Bilal').count(), 1)

    def test_different_number_is_fine(self):
        self._create(contact_number='03111234567')
        self.assertEqual(Customer.objects.filter(name='Bilal').count(), 1)

    def test_email_duplicate_ignores_case(self):
        Customer.objects.filter(pk=self.first.pk).update(email='ali@example.com')
        self._create(contact_number='03111234567', email='ALI@Example.com')
        self.assertEqual(Customer.objects.filter(name='Bilal').count(), 0)

    def test_update_only_checks_when_number_changes(self):
        dup = Customer.objects.create(name='Dup', contact_number='03001234567')   # pehle se duplicate
        r = self.client.post(reverse('customer_update', args=[dup.pk]),
                             {'name': 'Dup Renamed', 'contact_number': '+923001234567', 'address': 'x'})
        dup.refresh_from_db()
        self.assertEqual(dup.name, 'Dup Renamed')      # number nahi badla -> edit ho gaya

        self.client.post(reverse('customer_update', args=[dup.pk]),
                         {'name': 'Dup Renamed', 'contact_number': '0300 1234567 ', 'address': 'y'})
        dup.refresh_from_db()
        self.assertEqual(dup.address, 'y')             # sirf format badla -> abhi bhi allowed

        other = Customer.objects.create(name='Other', contact_number='03211234567')
        self.client.post(reverse('customer_update', args=[other.pk]),
                         {'name': 'Other', 'contact_number': '0300-1234567', 'address': 'z'})
        other.refresh_from_db()
        self.assertEqual(other.contact_number, '03211234567')   # doosre ka number lena -> blocked


class VendorDuplicateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.client.force_login(self.admin)
        self.first = Vendor.objects.create(name='Khan Traders', contact_number='0300-1234567')

    def test_vendor_create_blocks_same_number_any_format(self):
        self.client.post(reverse('vendor_create'),
                         {'name': 'Other Name', 'contact_number': '+923001234567', 'opening_balance': '0'})
        self.assertEqual(Vendor.objects.count(), 1)

    def test_vendor_create_same_name_only_warns(self):
        self.client.post(reverse('vendor_create'),
                         {'name': 'khan traders', 'contact_number': '03211234567', 'opening_balance': '0'})
        self.assertEqual(Vendor.objects.count(), 2)

    def test_vendor_update_cannot_take_other_vendors_number(self):
        other = Vendor.objects.create(name='Other', contact_number='03211234567')
        self.client.post(reverse('vendor_update', args=[other.pk]),
                         {'name': 'Other', 'contact_number': '+92 300 1234567', 'opening_balance': '0'})
        other.refresh_from_db()
        self.assertEqual(other.contact_number, '03211234567')


class ShopRegisterDuplicateTests(TestCase):
    def test_vendor_register_blocked_if_erp_vendor_has_same_number_in_other_format(self):
        Vendor.objects.create(name='Khan Traders', contact_number='0300-1234567')
        self.client.post(reverse('vendor_register'), {
            'business_name': 'New Shop', 'full_name': 'Ali Khan', 'phone': '03001234567',
            'email': 'new@example.com', 'city': 'Lahore', 'address': 'House 1, Street 2, Lahore',
            'password': 'secret12', 'confirm_password': 'secret12'})
        self.assertEqual(Vendor.objects.count(), 1)


class DuplicateReportTests(TestCase):
    def test_report_lists_duplicates(self):
        admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.client.force_login(admin)
        Customer.objects.create(name='Ali', contact_number='0300-1234567')
        Customer.objects.create(name='Ali Dup', contact_number='+923001234567')
        r = self.client.get(reverse('duplicate_report'))
        self.assertContains(r, '+923001234567')
        self.assertContains(r, 'Ali Dup')

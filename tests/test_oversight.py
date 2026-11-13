"""
Django tests: admin alerts (naya vendor / naya dispute), overview dashboard, vendor performance report.

Copy this file to app/tests_oversight.py and run:
    python manage.py test app.tests_oversight

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models (SaleOrder / DeliveryInfo / OrderReview required fields), fix that line in setUp
(the assertions themselves are the important part).
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import (AccountActionLog, Customer, CustomerProfile, DeliveryInfo, Notification, OrderDispute,
                        OrderReview, SaleOrder, Vendor, VendorProfile)
from app.utils.admin_alerts import alert_admins


class AdminAlertTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.staff = User.objects.create_user('clerk', 'clerk@example.com', 'x', is_staff=True)

    def test_alert_goes_to_superusers_only(self):
        n = alert_admins('Test alert', 'hello', link='/x/')
        self.assertEqual(n, 1)
        self.assertEqual(Notification.objects.filter(user=self.admin, title__icontains='Test alert').count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.staff).count(), 0)

    def test_alert_never_raises(self):
        self.admin.delete()
        self.assertEqual(alert_admins('Nobody home', 'x'), 0)

    def test_new_vendor_registration_alerts_admin(self):
        self.client.post(reverse('vendor_register'), {
            'business_name': 'Khan Traders', 'full_name': 'Ali Khan', 'phone': '03001234567',
            'email': 'khan@example.com', 'city': 'Lahore', 'address': 'House 1, Street 2, Lahore',
            'password': 'Secret#12345', 'confirm_password': 'Secret#12345'})
        self.assertTrue(Notification.objects.filter(user=self.admin, title__icontains='Naya vendor').exists())

    def test_new_dispute_alerts_admin(self):
        from app.customer.disputes import open_dispute
        vendor = Vendor.objects.create(name='Khan Traders', contact_number='03001234567')
        customer = Customer.objects.create(name='Ali', contact_number='03211234567')
        order = SaleOrder.objects.create(order_no='O-1', customer=customer, vendor=vendor, status='delivered')
        open_dispute(order, 'bad_quality', 'kharab maal')
        self.assertTrue(Notification.objects.filter(user=self.admin, title__icontains='Naya dispute').exists())


class OversightPagesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.client.force_login(self.admin)
        self.customer = Customer.objects.create(name='Ali', contact_number='03211234567')
        self.vendor = Vendor.objects.create(name='Khan Traders', contact_number='03001234567')
        vuser = User.objects.create_user('vendor_1', 'v@example.com', 'secret12')
        self.vp = VendorProfile.objects.create(vendor=self.vendor, user=vuser, business_name='Khan Traders',
                                               city='Lahore', is_approved=True)

    def _order(self, no, status, **kw):
        return SaleOrder.objects.create(order_no=no, customer=self.customer, vendor=self.vendor, status=status, **kw)

    def test_dashboard_counts(self):
        cuser = User.objects.create_user('c1', 'c1@example.com', 'x')
        CustomerProfile.objects.create(customer=self.customer, user=cuser, is_suspended=True)
        o = self._order('O-1', 'delivered')
        OrderDispute.objects.create(sale_order=o, customer=self.customer, vendor=self.vendor, reason='late')
        AccountActionLog.objects.create(kind='customer', name='Ali', action='suspend', by_name='boss')
        r = self.client.get(reverse('oversight_dashboard'))
        self.assertEqual(r.status_code, 200)
        c = r.context['cards']
        self.assertEqual(c['open_disputes'], 1)
        self.assertEqual(c['suspended_customers'], 1)
        self.assertEqual(c['new_vendors'], 1)
        self.assertEqual(c['orders_today'], 1)

    def test_performance_numbers(self):
        for i in range(3):
            self._order(f'D-{i}', 'delivered')
        self._order('C-1', 'cancelled', reject_reason='Stock nahi')
        o = self._order('R-1', 'delivered', vendor_responded_at=timezone.now() + timedelta(minutes=10))
        DeliveryInfo.objects.create(sale_order=o, status='delivered',
                                    delivered_at=timezone.now() + timedelta(minutes=50))
        OrderReview.objects.create(sale_order=o, vendor=self.vendor, vendor_rating=4)
        r = self.client.get(reverse('vendor_performance'))
        row = r.context['rows'][0]
        self.assertEqual(row['orders'], 5)
        self.assertEqual(row['delivered'], 4)
        self.assertEqual(row['cancelled'], 1)
        self.assertEqual(row['rejected'], 1)
        self.assertEqual(row['cancel_rate'], 20.0)
        self.assertEqual(row['rating'], 4.0)
        self.assertAlmostEqual(row['delivery_min'], 50.0, delta=1)
        self.assertAlmostEqual(row['response_min'], 10.0, delta=1)
        self.assertEqual(row['flags'], ['Cancel 20%'])

    def test_empty_vendors_hidden_by_default_but_can_be_shown(self):
        self.assertEqual(self.client.get(reverse('vendor_performance')).context['rows'], [])
        r = self.client.get(reverse('vendor_performance') + '?f=1')            # checkbox band = sab dikhao
        self.assertEqual(len(r.context['rows']), 1)

    def test_other_vendors_orders_not_mixed(self):
        other = Vendor.objects.create(name='Other', contact_number='03331234567')
        SaleOrder.objects.create(order_no='X-1', customer=self.customer, vendor=other, status='delivered')
        self._order('M-1', 'delivered')
        rows = self.client.get(reverse('vendor_performance') + '?f=1').context['rows']
        mine = [r for r in rows if r['vendor_id'] == self.vendor.pk][0]
        self.assertEqual(mine['orders'], 1)

    def test_bad_params_do_not_crash_and_csv_works(self):
        self.assertEqual(self.client.get(reverse('vendor_performance') + '?days=abc&sort=zzz').status_code, 200)
        self._order('D-1', 'delivered')
        r = self.client.get(reverse('vendor_performance') + '?export=csv')
        self.assertEqual(r['Content-Type'].split(';')[0], 'text/csv')
        self.assertIn('Khan Traders', r.content.decode('utf-8'))

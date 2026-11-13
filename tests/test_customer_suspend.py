"""
Django tests: customer account suspend / unsuspend.

Copy this file to app/tests_customer_suspend.py and run:
    python manage.py migrate
    python manage.py test app.tests_customer_suspend

NOTE: written without a Django install to run it on - if a fixture field name differs from your
models, fix that line in setUp (the assertions themselves are the important part).
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from app.models import Customer, CustomerProfile, SaleOrder


class CustomerSuspendTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('boss', 'boss@example.com', 'adminpass1')
        self.customer = Customer.objects.create(name='Ali', contact_number='+923001112223')
        self.user = User.objects.create_user('cust_ali', 'ali@example.com', 'secret12')
        self.profile = CustomerProfile.objects.create(customer=self.customer, user=self.user)

    def _suspend(self, reason='Fraud'):
        self.client.force_login(self.admin)
        return self.client.post(
            reverse('customer_suspend_action', args=[self.customer.pk, 'suspend']),
            {'reason': reason})

    def test_admin_can_suspend_and_unsuspend(self):
        self._suspend('Fake orders')
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_suspended)
        self.assertEqual(self.profile.suspended_reason, 'Fake orders')
        self.assertEqual(self.profile.suspended_by, self.admin)
        self.assertIsNotNone(self.profile.suspended_at)

        self.client.post(reverse('customer_suspend_action', args=[self.customer.pk, 'unsuspend']))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_suspended)
        self.assertEqual(self.profile.suspended_reason, '')
        self.assertIsNone(self.profile.suspended_by)

    def test_get_request_does_not_suspend(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('customer_suspend_action', args=[self.customer.pk, 'suspend']))
        self.assertEqual(r.status_code, 405)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_suspended)

    def test_customer_cannot_suspend_anyone(self):
        self.client.force_login(self.user)
        self.client.post(reverse('customer_suspend_action', args=[self.customer.pk, 'suspend']))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_suspended)

    def test_suspended_customer_cannot_login(self):
        self._suspend()
        self.client.logout()
        r = self.client.post(reverse('customer_login'),
                             {'phone': '03001112223', 'password': 'secret12'}, follow=True)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(r, 'suspend')

    def test_wrong_password_does_not_reveal_suspension(self):
        self._suspend()
        self.client.logout()
        r = self.client.post(reverse('customer_login'),
                             {'phone': '03001112223', 'password': 'wrong'}, follow=True)
        self.assertNotContains(r, 'suspend kar diya')

    def test_existing_session_is_logged_out_on_next_page(self):
        customer_client = Client()
        customer_client.force_login(self.user)      # customer pehle se login hai
        self._suspend()                             # admin (alag client) suspend karta hai
        r = customer_client.get(reverse('my_orders'))
        self.assertRedirects(r, reverse('customer_login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', customer_client.session)

    def test_suspended_customer_cannot_place_order(self):
        self.profile.is_suspended = True
        self.profile.save()
        self.client.force_login(self.user)
        r = self.client.post(reverse('place_order'), {'payment_method': 'cod'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SaleOrder.objects.count(), 0)

    def test_unsuspended_customer_can_login_again(self):
        self._suspend()
        self.client.post(reverse('customer_suspend_action', args=[self.customer.pk, 'unsuspend']))
        self.client.logout()
        self.client.post(reverse('customer_login'),
                         {'phone': '03001112223', 'password': 'secret12'})
        self.assertIn('_auth_user_id', self.client.session)

    def test_suspended_filter_in_customer_list(self):
        self._suspend()
        r = self.client.get(reverse('customer_list') + '?status=suspended')
        self.assertContains(r, 'Ali')
        self.assertContains(r, 'SUSPENDED')

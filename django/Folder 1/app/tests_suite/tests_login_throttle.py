"""
Customer login/register throttle tests.

Run:  python manage.py test app.tests_suite.tests_login_throttle
"""
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app.customer import views_customer_auth as auth_views
from app.models import Customer, CustomerProfile

PHONE_LOCAL = '03003333333'
PHONE_DB = '+923003333333'


def msgs(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('cust', 'c@x.com', 'secret12')
        self.customer = Customer.objects.create(
            name='Zara', contact_number=PHONE_DB, address='Lahore')
        CustomerProfile.objects.create(customer=self.customer, user=self.user)
        self.url = reverse('customer_login')

    def _login(self, phone=PHONE_LOCAL, password='wrong-pass'):
        return self.client.post(self.url, {'phone': phone, 'password': password})

    def test_lock_after_max_failures_even_with_correct_password(self):
        for _ in range(auth_views.LOGIN_MAX_ATTEMPTS):
            r = self._login()
            self.assertIn(auth_views.LOGIN_FAILED_MSG, msgs(r))
        r = self._login(password='secret12')          # sahi password, magar lock
        self.assertIn(auth_views.LOGIN_LOCKED_MSG, msgs(r))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_success_resets_counter(self):
        for _ in range(auth_views.LOGIN_MAX_ATTEMPTS - 1):
            self._login()
        r = self._login(password='secret12')
        self.assertEqual(r.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)
        self.client.logout()
        r = self._login()                              # counter zero se shuru
        self.assertIn(auth_views.LOGIN_FAILED_MSG, msgs(r))

    def test_unknown_phone_and_wrong_password_look_the_same(self):
        a = msgs(self._login(phone='03009999999'))
        b = msgs(self._login())
        self.assertEqual(a, b)

    def test_unknown_phones_are_counted_too(self):
        for _ in range(auth_views.LOGIN_MAX_ATTEMPTS):
            self._login(phone='03009999999')
        self.assertIn(auth_views.LOGIN_LOCKED_MSG, msgs(self._login(phone='03009999999')))

    def test_other_phone_is_not_locked_by_one_phone(self):
        for _ in range(auth_views.LOGIN_MAX_ATTEMPTS):
            self._login()
        self.assertNotIn(auth_views.LOGIN_LOCKED_MSG, msgs(self._login(phone='03008888888')))

    def test_ip_wide_limit(self):
        for i in range(auth_views.LOGIN_MAX_ATTEMPTS_PER_IP):
            self._login(phone=f'0300{i:07d}')
        self.assertIn(auth_views.LOGIN_LOCKED_MSG, msgs(self._login(phone='03007777777')))


class RegisterThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_register_attempts_are_limited(self):
        url = reverse('customer_register')
        for _ in range(auth_views.REGISTER_MAX_PER_HOUR):
            self.client.post(url, {})
        r = self.client.post(url, {})
        self.assertTrue(any('Bohat zyada' in m for m in msgs(r)))

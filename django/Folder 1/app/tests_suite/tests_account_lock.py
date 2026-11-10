"""
Per-account lockout tests.

Run:  python manage.py test app.tests_suite.tests_account_lock
"""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timedelta

# The rule is pure, so it can be tested without Django (loaded straight from the file).
_spec = importlib.util.spec_from_file_location(
    "account_lock_pure", pathlib.Path(__file__).resolve().parent.parent / "security" / "account_lock.py")
_pure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pure)


class LockRuleTests(unittest.TestCase):
    NOW = datetime(2026, 1, 1, 12, 0, 0)

    def fails(self, n, minutes_ago_first=10, gap=1):
        return [self.NOW - timedelta(minutes=minutes_ago_first - i * gap) for i in range(n)]

    def test_threshold_doubles_ip_limit_with_floor(self):
        self.assertEqual(_pure.lock_threshold(5), 10)
        self.assertEqual(_pure.lock_threshold(2), 6)
        self.assertEqual(_pure.lock_threshold(0), 6)

    def test_below_threshold_is_free(self):
        self.assertEqual(_pure.minutes_until_unlock(self.fails(9), 10, 30, self.NOW), 0)

    def test_at_threshold_locks_until_oldest_ages_out(self):
        # failures at -10 ... -1 min, window 30: oldest leaves the window in 20 min
        self.assertEqual(_pure.minutes_until_unlock(self.fails(10), 10, 30, self.NOW), 20)

    def test_more_failures_lock_longer(self):
        # 12 failures, threshold 10 -> the 3rd oldest must expire (index 2)
        t = [self.NOW - timedelta(minutes=12 - i) for i in range(12)]
        self.assertEqual(_pure.minutes_until_unlock(t, 10, 30, self.NOW), 30 - 10)

    def test_old_failures_do_not_count(self):
        old = [self.NOW - timedelta(minutes=45 + i) for i in range(20)]
        self.assertEqual(_pure.minutes_until_unlock(old, 10, 30, self.NOW), 0)


try:
    from django.core import mail
    from django.core.cache import cache
    from django.test import Client, TestCase, override_settings
    from django.contrib.auth.models import User
    from app.models import IPWhitelist, LoginAttempt, SecurityAlert, SecuritySettings
    from app.security import account_lock
    from app.utils.security import track_login_attempt
except Exception:            # no Django / settings: only the pure tests above run
    TestCase = None

if TestCase is not None:
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    class AccountLockDbTests(TestCase):
        def setUp(self):
            cache.clear()
            s = SecuritySettings.get_settings()
            s.max_login_attempts = 3          # threshold = 6
            s.lockout_time = 30
            s.alert_email = "owner@example.com"
            s.enable_security_alerts = True
            s.save()

        def _spray(self, username, n):
            for i in range(n):                 # a different IP each time: the IP block never triggers
                track_login_attempt(username, f"10.0.0.{i + 1}", "bot", False, "bad")

        def test_spread_attack_locks_account_and_emails_once(self):
            self._spray("ali", 6)
            self.assertGreater(account_lock.account_lock_minutes("ali"), 0)
            self.assertGreater(account_lock.account_lock_minutes("ALI"), 0)     # case-insensitive
            self.assertEqual(SecurityAlert.objects.filter(title__startswith="Account locked").count(), 1)
            self.assertEqual(len(mail.outbox), 1)

        def test_five_failures_do_not_lock(self):
            self._spray("sara", 5)
            self.assertEqual(account_lock.account_lock_minutes("sara"), 0)

        def test_login_post_is_refused_even_with_correct_password(self):
            User.objects.create_user("bilal", "b@example.com", "Correct-pass-1")
            self._spray("bilal", 6)
            r = Client().post("/login/", {"username": "bilal", "password": "Correct-pass-1"})
            self.assertEqual(r.status_code, 429)
            self.assertIn("Retry-After", r)

        def test_unknown_and_known_usernames_get_the_same_answer(self):
            User.objects.create_user("real", "r@example.com", "x")
            self._spray("real", 6)
            self._spray("ghost", 6)
            a = Client().post("/login/", {"username": "real", "password": "x"})
            b = Client().post("/login/", {"username": "ghost", "password": "x"})
            self.assertEqual((a.status_code, b.status_code), (429, 429))

        def test_whitelisted_ip_is_never_locked_out(self):
            IPWhitelist.objects.create(ip_address="203.0.113.7", is_active=True)
            self._spray("owner", 6)
            r = Client().post("/login/", {"username": "owner", "password": "x"}, REMOTE_ADDR="203.0.113.7")
            self.assertNotEqual(r.status_code, 429)

        def test_admin_unlock_resets_and_keeps_history(self):
            admin = User.objects.create_superuser("boss", "boss@example.com", "pw")
            self._spray("zain", 6)
            before = LoginAttempt.objects.filter(username="zain").count()
            account_lock.unlock_account("zain", admin)
            self.assertEqual(account_lock.account_lock_minutes("zain"), 0)
            self.assertEqual(LoginAttempt.objects.filter(username="zain").count(), before + 1)

        def test_successful_login_resets_count(self):
            self._spray("noor", 4)
            track_login_attempt("noor", "10.9.9.9", "ok", True)
            self._spray("noor", 4)
            self.assertEqual(account_lock.account_lock_minutes("noor"), 0)

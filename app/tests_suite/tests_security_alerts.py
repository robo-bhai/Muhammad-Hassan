"""
Security alert email + brute-force record tests.

Run:  python manage.py test app.tests_suite.tests_security_alerts
"""
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from app.models import IPBlacklist, LoginAttempt, SecurityAlert, SecuritySettings
from app.utils.security import create_security_alert, track_login_attempt


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SecurityAlertMailTests(TestCase):
    def setUp(self):
        cache.clear()
        s = SecuritySettings.get_settings()
        s.enable_security_alerts = True
        s.alert_email = "owner@example.com"
        s.max_login_attempts = 3
        s.save()

    def test_high_alert_is_emailed_once_per_ip(self):
        create_security_alert("Test", "details", "brute_force", "high", ip_address="9.9.9.9")
        create_security_alert("Test", "details", "brute_force", "high", ip_address="9.9.9.9")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])
        self.assertIn("9.9.9.9", mail.outbox[0].body)

    def test_low_alert_is_not_emailed(self):
        create_security_alert("Password changed", "x", "password_change", "low")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(SecurityAlert.objects.count(), 1)

    def test_switch_off_means_no_email(self):
        s = SecuritySettings.get_settings(); s.enable_security_alerts = False; s.save()
        create_security_alert("Test", "x", "brute_force", "high", ip_address="9.9.9.9")
        self.assertEqual(len(mail.outbox), 0)

    def test_falls_back_to_superuser_email(self):
        s = SecuritySettings.get_settings(); s.alert_email = ""; s.save()
        User.objects.create_superuser("boss", "boss@example.com", "pw")
        create_security_alert("Test", "x", "unauthorized_access", "medium", ip_address="1.1.1.1")
        self.assertEqual(mail.outbox[0].to, ["boss@example.com"])

    def test_brute_force_blocks_ip_records_details_and_emails(self):
        for name in ("admin", "root", "test"):
            track_login_attempt(name, "8.8.4.4", "sqlmap/1.7", False, "Invalid username or password")
        self.assertTrue(IPBlacklist.objects.filter(ip_address="8.8.4.4", is_active=True).exists())
        self.assertEqual(LoginAttempt.objects.filter(ip_address="8.8.4.4").count(), 3)
        alert = SecurityAlert.objects.get(alert_type="brute_force")
        for needle in ("admin", "root", "sqlmap/1.7"):
            self.assertIn(needle, alert.description)
        self.assertEqual(len(mail.outbox), 1)

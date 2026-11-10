"""
New-device login alert tests.

Run:  python manage.py test app.tests_suite.tests_new_device
"""
import importlib.util
import pathlib
import unittest

_spec = importlib.util.spec_from_file_location(
    "new_device_pure", pathlib.Path(__file__).resolve().parent.parent / "security" / "new_device.py")
_nd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_nd)

CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
CHROME_WIN_NEW = CHROME_WIN.replace("126.0", "130.0")
EDGE_WIN = CHROME_WIN + " Edg/126.0"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
ANDROID = "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"


class DeviceRuleTests(unittest.TestCase):
    def test_signatures(self):
        sig = _nd.device_signature
        self.assertEqual(sig(CHROME_WIN), "Chrome|Windows")
        self.assertEqual(sig(EDGE_WIN), "Edge|Windows")
        self.assertEqual(sig(IPHONE), "Safari|iOS")
        self.assertEqual(sig(ANDROID), "Chrome|Android")
        self.assertEqual(sig(FIREFOX), "Firefox|Linux")
        self.assertEqual(sig(""), "")
        self.assertEqual(sig(None), "")

    def test_browser_update_is_not_a_new_device(self):
        self.assertFalse(_nd.is_new_device([CHROME_WIN], CHROME_WIN_NEW))

    def test_different_browser_or_os_is_new(self):
        self.assertTrue(_nd.is_new_device([CHROME_WIN], EDGE_WIN))
        self.assertTrue(_nd.is_new_device([CHROME_WIN], IPHONE))

    def test_first_ever_login_is_not_flagged(self):
        self.assertFalse(_nd.is_new_device([], CHROME_WIN))
        self.assertFalse(_nd.is_new_device(["", None], CHROME_WIN))

    def test_missing_user_agent_is_not_flagged(self):
        self.assertFalse(_nd.is_new_device([CHROME_WIN], ""))

    def test_known_among_several(self):
        self.assertFalse(_nd.is_new_device([IPHONE, CHROME_WIN], CHROME_WIN_NEW))


try:
    from django.contrib.auth.models import User
    from django.core import mail
    from django.test import TestCase, override_settings
    from app.models import SecurityAlert
    from app.utils.security import track_login_attempt
except Exception:
    TestCase = None

if TestCase is not None:
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    class NewDeviceDbTests(TestCase):
        def setUp(self):
            self.user = User.objects.create_user("hina", "hina@example.com", "pw")

        def test_flow(self):
            track_login_attempt("hina", "1.1.1.1", CHROME_WIN, True)         # first login: silent
            self.assertEqual(len(mail.outbox), 0)
            track_login_attempt("hina", "1.1.1.2", CHROME_WIN_NEW, True)     # same device: silent
            self.assertEqual(len(mail.outbox), 0)
            track_login_attempt("hina", "9.9.9.9", IPHONE, True)             # new device: email
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, ["hina@example.com"])
            self.assertIn("9.9.9.9", mail.outbox[0].body)
            self.assertEqual(SecurityAlert.objects.filter(user=self.user, severity="low").count(), 1)
            track_login_attempt("hina", "9.9.9.9", IPHONE, True)             # now known: silent
            self.assertEqual(len(mail.outbox), 1)

        def test_failed_login_never_flags(self):
            track_login_attempt("hina", "1.1.1.1", CHROME_WIN, True)
            track_login_attempt("hina", "9.9.9.9", IPHONE, False, "bad")
            self.assertEqual(len(mail.outbox), 0)

        def test_user_without_email_still_logs_alert_without_crash(self):
            self.user.email = ""; self.user.save()
            track_login_attempt("hina", "1.1.1.1", CHROME_WIN, True)
            track_login_attempt("hina", "9.9.9.9", IPHONE, True)
            self.assertEqual(len(mail.outbox), 0)
            self.assertEqual(SecurityAlert.objects.count(), 1)

        @override_settings(SECURITY_NEW_DEVICE_ALERTS=False)
        def test_can_be_switched_off(self):
            track_login_attempt("hina", "1.1.1.1", CHROME_WIN, True)
            track_login_attempt("hina", "9.9.9.9", IPHONE, True)
            self.assertEqual(len(mail.outbox), 0)

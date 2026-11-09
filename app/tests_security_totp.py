"""
TOTP / backup-code tests (pure logic, no database).

Run:  python manage.py test app.tests_security_totp
"""
import unittest

from app.security import totp


class TotpTests(unittest.TestCase):
    # RFC 6238 test vector: secret "12345678901234567890", SHA-1, 8 digits -> we use 6, so
    # compare the last 6 digits of the published values.
    SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_rfc6238_vectors(self):
        self.assertEqual(totp.totp_at(self.SECRET, 59), "287082")
        self.assertEqual(totp.totp_at(self.SECRET, 1111111109), "081804")
        self.assertEqual(totp.totp_at(self.SECRET, 2000000000), "279037")

    def test_verify_window_and_rejects(self):
        t = 1111111109
        code = totp.totp_at(self.SECRET, t)
        self.assertIsNotNone(totp.verify_totp(self.SECRET, code, for_time=t))
        self.assertIsNotNone(totp.verify_totp(self.SECRET, code, for_time=t + 30))   # drift
        self.assertIsNone(totp.verify_totp(self.SECRET, code, for_time=t + 120))     # too old
        self.assertIsNone(totp.verify_totp(self.SECRET, "000000", for_time=t))
        self.assertIsNone(totp.verify_totp(self.SECRET, "abc", for_time=t))
        self.assertIsNone(totp.verify_totp(self.SECRET, "", for_time=t))

    def test_secret_and_uri(self):
        s = totp.generate_secret()
        self.assertEqual(len(s), 32)
        self.assertNotEqual(s, totp.generate_secret())
        uri = totp.provisioning_uri(s, "ali@x.com", "My ERP")
        self.assertTrue(uri.startswith("otpauth://totp/My%20ERP%3Aali%40x.com?secret=" + s))

    def test_backup_codes_single_use(self):
        plain, hashes = totp.new_backup_codes()
        self.assertEqual(len(plain), totp.BACKUP_CODE_COUNT)
        self.assertNotIn(plain[0], hashes)               # only hashes are stored
        left = totp.consume_backup_code(hashes, plain[0])
        self.assertEqual(len(left), len(hashes) - 1)
        self.assertIsNone(totp.consume_backup_code(left, plain[0]))   # second use fails
        self.assertIsNotNone(totp.consume_backup_code(left, plain[1].replace("-", "").upper()))
        self.assertIsNone(totp.consume_backup_code(hashes, "zzzz-zzzz"))


if __name__ == "__main__":
    unittest.main()

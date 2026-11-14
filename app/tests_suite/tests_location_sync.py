from django.test import SimpleTestCase

from app.customer.location_sync import resolve_capture as rc

NOW = 1_000_000.0


class ResolveCaptureTests(SimpleTestCase):
    def test_live_point(self):
        self.assertEqual(rc(None, NOW, None), (NOW, 'ok'))
        self.assertEqual(rc('', NOW, NOW - 100), (NOW, 'ok'))

    def test_live_rate_limited(self):
        self.assertEqual(rc(None, NOW, NOW - 1), (None, 'rate'))

    def test_queued_newer_than_last_is_used_with_its_own_time(self):
        self.assertEqual(rc(NOW - 300, NOW, NOW - 900), (NOW - 300, 'ok'))

    def test_queued_older_than_last_is_dropped(self):
        self.assertEqual(rc(NOW - 900, NOW, NOW - 300), (None, 'older'))
        self.assertEqual(rc(NOW - 300, NOW, NOW - 300), (None, 'older'))

    def test_too_old(self):
        self.assertEqual(rc(NOW - 7 * 3600, NOW, None), (None, 'too_old'))

    def test_future_time_is_clamped_to_now(self):
        self.assertEqual(rc(NOW + 3000, NOW, None), (NOW, 'ok'))
        self.assertEqual(rc(NOW + 30, NOW, None), (NOW, 'ok'))   # thora aage: now se zyada nahi

    def test_garbage_at_falls_back_to_live(self):
        self.assertEqual(rc('abc', NOW, None), (NOW, 'ok'))
        self.assertEqual(rc('nan', NOW, None), (NOW, 'ok'))
        self.assertEqual(rc('inf', NOW, None), (NOW, 'ok'))

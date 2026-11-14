from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from app.customer import goals as g


class GoalsTests(SimpleTestCase):
    def test_week_start_is_monday(self):
        self.assertEqual(g.week_start(date(2026, 11, 13)), date(2026, 11, 9))   # Jumma -> Peer
        self.assertEqual(g.week_start(date(2026, 11, 9)), date(2026, 11, 9))
        self.assertEqual(g.week_start(date(2026, 11, 15)), date(2026, 11, 9))   # Itwaar

    def test_progress_off(self):
        self.assertIsNone(g.progress(5, 0, 100))

    def test_progress_partial_and_reached(self):
        p = g.progress(4, 10, 200)
        self.assertEqual((p['pct'], p['left'], p['reached']), (40, 6, False))
        p = g.progress(12, 10, 200)
        self.assertEqual((p['pct'], p['left'], p['reached']), (100, 0, True))
        self.assertEqual(p['bonus'], Decimal('200'))

    def test_cash_state(self):
        self.assertIsNone(g.cash_state(5000, 0))
        self.assertEqual(g.cash_state(1000, 10000)['level'], 'ok')
        self.assertEqual(g.cash_state(8000, 10000)['level'], 'warn')
        self.assertEqual(g.cash_state(10000, 10000)['level'], 'over')
        self.assertEqual(g.cash_state(25000, 10000)['pct'], 100)
        self.assertEqual(g.cash_state(-50, 10000)['pct'], 0)

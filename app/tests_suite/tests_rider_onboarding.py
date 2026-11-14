from datetime import date, datetime, time

from django.test import SimpleTestCase

from app.customer import rider_docs as rd
from app.customer import shifts as sh

TODAY = date(2026, 11, 14)


def D(kind, status='approved', expiry=None):
    return {'kind': kind, 'status': status, 'expiry': expiry}


class DocsTests(SimpleTestCase):
    def test_all_missing(self):
        ev = rd.evaluate([], TODAY)
        self.assertEqual(ev['missing'], rd.REQUIRED)
        self.assertFalse(ev['complete'])

    def test_complete(self):
        docs = [D(k, expiry=date(2027, 12, 1) if k in rd.NEEDS_EXPIRY else None) for k in rd.REQUIRED]
        ev = rd.evaluate(docs, TODAY)
        self.assertTrue(ev['complete'])
        self.assertEqual(rd.blocking(ev), [])

    def test_pending_and_rejected_not_complete(self):
        docs = [D('cpr'), D('license', 'pending'), D('vehicle', 'rejected'), D('photo')]
        ev = rd.evaluate(docs, TODAY)
        self.assertFalse(ev['complete'])
        self.assertEqual(ev['pending'], ['license'])
        self.assertEqual(rd.blocking(ev), ['vehicle'])

    def test_expired_blocks_and_expiring_warns(self):
        docs = [D('cpr', expiry=date(2026, 11, 1)), D('license', expiry=date(2026, 12, 1)),
                D('vehicle'), D('photo')]
        ev = rd.evaluate(docs, TODAY)
        self.assertEqual(ev['expired'], ['cpr'])
        self.assertEqual(ev['expiring'], ['license'])
        self.assertEqual(rd.blocking(ev), ['cpr'])
        self.assertFalse(ev['complete'])

    def test_expiry_today_is_still_valid(self):
        ev = rd.evaluate([D('cpr', expiry=TODAY)], TODAY, required=['cpr'])
        self.assertEqual(ev['expired'], [])


class ShiftTests(SimpleTestCase):
    def test_bounds_overnight(self):
        s, e = sh.bounds(TODAY, time(22, 0), time(2, 0))
        self.assertEqual(e, datetime(2026, 11, 15, 2, 0))
        s, e = sh.bounds(TODAY, time(12, 0), time(16, 0))
        self.assertEqual(e, datetime(2026, 11, 14, 16, 0))

    def test_overlaps(self):
        a = sh.bounds(TODAY, time(12), time(16))
        self.assertTrue(sh.overlaps(a, sh.bounds(TODAY, time(15), time(18))))
        self.assertFalse(sh.overlaps(a, sh.bounds(TODAY, time(16), time(18))))   # sirf chhune wali
        self.assertTrue(sh.overlaps(sh.bounds(TODAY, time(22), time(2)), sh.bounds(date(2026, 11, 15), time(1), time(3))))

    def test_can_cancel(self):
        start = datetime(2026, 11, 14, 18, 0)
        self.assertTrue(sh.can_cancel(start, datetime(2026, 11, 14, 15, 59), 2))
        self.assertFalse(sh.can_cancel(start, datetime(2026, 11, 14, 16, 1), 2))

    def test_in_shift_with_grace(self):
        w = [sh.bounds(TODAY, time(18), time(23))]
        self.assertTrue(sh.in_shift(w, datetime(2026, 11, 14, 17, 50)))
        self.assertFalse(sh.in_shift(w, datetime(2026, 11, 14, 17, 30)))
        self.assertTrue(sh.in_shift(w, datetime(2026, 11, 14, 23, 0)))
        self.assertFalse(sh.in_shift(w, datetime(2026, 11, 14, 23, 1)))

    def test_next_window(self):
        a, b = sh.bounds(TODAY, time(12), time(16)), sh.bounds(TODAY, time(18), time(23))
        self.assertEqual(sh.next_window([b, a], datetime(2026, 11, 14, 13, 0)), a)   # chal rahi
        self.assertEqual(sh.next_window([b, a], datetime(2026, 11, 14, 17, 0)), b)
        self.assertIsNone(sh.next_window([a], datetime(2026, 11, 14, 17, 0)))

    def test_parse_slots(self):
        self.assertEqual(sh.parse_slots('12:00-16:00, 18:00-23:30'),
                         [(time(12), time(16)), (time(18), time(23, 30))])
        for bad in ('', 'abc', '12:00', '10:00-10:00', '25:00-26:00'):
            with self.assertRaises(ValueError):
                sh.parse_slots(bad)

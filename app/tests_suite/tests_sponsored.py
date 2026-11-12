"""
Tests: Sponsored / Featured store (app/customer/sponsored.py + StoreSponsorship.activate).

Run:  python manage.py test app.tests_suite.tests_sponsored -v 2

NOTE: written by reading the code, without a Django project to run it in. The database and the settings
are patched, so no fixtures are needed. Hand-calculated: activate(7) on 2026-11-12 -> 12 Nov .. 18 Nov
(the first day counts); a running sponsorship until 20 Nov -> the next one runs 21 Nov .. 27 Nov.
"""
from datetime import date
from decimal import Decimal as D
from unittest import mock

from django.test import SimpleTestCase

from app.customer import sponsored
from app.models import StoreSponsorship

TODAY = date(2026, 11, 12)
CFG = 'app.customer.sponsored.sponsored_settings'
MODEL = 'app.models.StoreSponsorship'


def cfg(enabled=True, max_slots=5):
    return {'enabled': enabled, 'price': D('1000'), 'days': 7, 'max_slots': max_slots}


def fake_model(profile_ids):
    m = mock.MagicMock()
    m.objects.filter.return_value.order_by.return_value.values_list.return_value = profile_ids
    return m


class ProfileIdsTests(SimpleTestCase):
    def test_flag_off_means_nobody_boosted(self):
        with mock.patch(CFG, return_value=cfg(enabled=False)), mock.patch(MODEL, fake_model([1, 2])):
            self.assertEqual(sponsored.sponsored_profile_ids(TODAY), set())

    def test_active_ids_returned(self):
        with mock.patch(CFG, return_value=cfg()), mock.patch(MODEL, fake_model([3, 1])):
            self.assertEqual(sponsored.sponsored_profile_ids(TODAY), {1, 3})

    def test_duplicates_collapse(self):
        with mock.patch(CFG, return_value=cfg(max_slots=2)), mock.patch(MODEL, fake_model([5, 5, 6, 7])):
            self.assertEqual(sponsored.sponsored_profile_ids(TODAY), {5, 6})   # 5 once, then 6; slot limit 2

    def test_max_slots_keeps_earliest(self):
        with mock.patch(CFG, return_value=cfg(max_slots=2)), mock.patch(MODEL, fake_model([10, 11, 12])):
            self.assertEqual(sponsored.sponsored_profile_ids(TODAY), {10, 11})

    def test_zero_slots_means_no_limit(self):
        with mock.patch(CFG, return_value=cfg(max_slots=0)), mock.patch(MODEL, fake_model([1, 2, 3, 4, 5, 6, 7])):
            self.assertEqual(len(sponsored.sponsored_profile_ids(TODAY)), 7)

    def test_error_gives_empty_set(self):
        with mock.patch(CFG, side_effect=RuntimeError('db down')):
            self.assertEqual(sponsored.sponsored_profile_ids(TODAY), set())


class ActivateTests(SimpleTestCase):
    def _activate(self, running_until=None, days=7):
        sp = StoreSponsorship(profile_id=1)
        running = mock.MagicMock(ends_on=running_until) if running_until else None
        qs = mock.MagicMock()
        qs.filter.return_value.exclude.return_value.order_by.return_value.first.return_value = running
        with mock.patch('app.models.trade.vendor_portal.timezone.localdate', return_value=TODAY), \
                mock.patch.object(StoreSponsorship, 'objects', qs), \
                mock.patch.object(StoreSponsorship, 'save'):
            sp.activate(days)
        return sp

    def test_starts_today(self):
        sp = self._activate()
        self.assertEqual((sp.starts_on, sp.ends_on, sp.status), (TODAY, date(2026, 11, 18), 'active'))

    def test_extends_after_running_one(self):
        sp = self._activate(running_until=date(2026, 11, 20))
        self.assertEqual((sp.starts_on, sp.ends_on), (date(2026, 11, 21), date(2026, 11, 27)))

    def test_minimum_one_day(self):
        sp = self._activate(days=0)
        self.assertEqual(sp.starts_on, sp.ends_on)

    def test_is_running(self):
        sp = StoreSponsorship(status='active', ends_on=TODAY)
        with mock.patch('app.models.trade.vendor_portal.timezone.localdate', return_value=TODAY):
            self.assertTrue(sp.is_running)
        with mock.patch('app.models.trade.vendor_portal.timezone.localdate', return_value=date(2026, 11, 13)):
            self.assertFalse(sp.is_running)

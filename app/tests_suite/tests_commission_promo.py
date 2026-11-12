"""
Tests: naye vendor ka launch commission offer (promo) - commission_percent, grant, expire.

Run:  python manage.py test app.tests_suite.tests_commission_promo -v 2

NOTE: written by reading the code, without a Django project to run it in. If a fixture line fails on
a field name, fix it in setUp - the assertions are what matter. The company margin rule and the batch
repricing are patched, so no stock fixtures are needed.

Hand-calculated numbers (normal commission 10%, today = 2026-11-12):
    no promo                          -> 10
    promo 0% till 2026-11-12 (today)  -> 0     (last day still counts)
    promo 0% till 2026-11-11          -> 10    (expired)
    promo 15% (higher than normal)    -> 10    (promo never raises the rate)
    company min margin 25% -> floor = 100 x 25 / 125 = 20.00%
        (cost = 80, price 100 -> margin 20/80 = 25%); promo 0% on normal 30% -> 20
    company min margin 0              -> floor 0
    grant: 60 days, 0% on 2026-11-12  -> until 2027-01-10 (12 Nov + 59 days; the approval day counts as day 1)
    grant twice                       -> second time does nothing
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from app.customer import vendor_commission as vc
from app.models import Vendor, VendorProfile

D = Decimal
TODAY = date(2026, 11, 12)
FLOOR = 'app.customer.vendor_commission.margin_floor_commission'
TODAY_FN = 'app.customer.vendor_commission.timezone.localdate'
DEFAULT = 'app.customer.vendor_commission.default_commission'
PROMO_CFG = 'app.customer.vendor_commission.launch_promo_settings'
REPRICE = 'app.customer.vendor_commission.reprice_vendor_batches'


def profile(promo=None, until=None, own=None):
    return SimpleNamespace(commission_percent=own, commission_promo_percent=promo, commission_promo_until=until)


class CommissionPercentTests(SimpleTestCase):
    def setUp(self):
        for target, value in ((DEFAULT, D('10')), (FLOOR, D('0')), (TODAY_FN, TODAY)):
            p = mock.patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_no_promo(self):
        self.assertEqual(vc.commission_percent(profile()), D('10'))

    def test_own_rate_when_no_promo(self):
        self.assertEqual(vc.commission_percent(profile(own=D('12.5'))), D('12.5'))

    def test_promo_on_last_day_counts(self):
        self.assertEqual(vc.commission_percent(profile(D('0'), TODAY)), D('0'))

    def test_promo_expired(self):
        self.assertEqual(vc.commission_percent(profile(D('0'), date(2026, 11, 11))), D('10'))

    def test_promo_never_raises_rate(self):
        self.assertEqual(vc.commission_percent(profile(D('15'), date(2026, 12, 1))), D('10'))

    def test_promo_beats_own_rate_when_lower(self):
        self.assertEqual(vc.commission_percent(profile(D('2'), date(2026, 12, 1), own=D('20'))), D('2'))

    def test_promo_needs_both_fields(self):
        self.assertEqual(vc.commission_percent(profile(D('0'), None)), D('10'))
        self.assertEqual(vc.commission_percent(profile(None, date(2026, 12, 1))), D('10'))

    def test_margin_floor_lifts_promo(self):
        with mock.patch(FLOOR, return_value=D('20.00')):
            self.assertEqual(vc.commission_percent(profile(D('0'), date(2026, 12, 1), own=D('30'))), D('20.00'))

    def test_margin_floor_above_normal_means_no_promo(self):
        with mock.patch(FLOOR, return_value=D('20.00')):
            self.assertEqual(vc.commission_percent(profile(D('0'), date(2026, 12, 1))), D('10'))


class MarginFloorTests(TestCase):
    def _floor(self, value):
        with mock.patch('app.models.SystemSetting.get_value', return_value=value):
            return vc.margin_floor_commission()

    def test_floor_maths(self):
        self.assertEqual(self._floor('25'), D('20.00'))
        self.assertEqual(self._floor('0'), D('0'))
        self.assertEqual(self._floor('10'), D('9.10'))   # 1000/110 = 9.0909 -> rounded UP to 9.10

    def test_bad_values_mean_no_floor(self):
        for bad in ('', 'abc', '-5', 'NaN', None):
            self.assertEqual(self._floor(bad), D('0'), bad)


class GrantAndExpireTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('v1', 'v1@x.com', 'pw12345!')
        self.vendor = Vendor.objects.create(name='New Shop')
        self.profile = VendorProfile.objects.create(
            vendor=self.vendor, user=self.user, business_name='New Shop', is_approved=True)
        for target in (FLOOR, DEFAULT):
            p = mock.patch(target, return_value=D('0') if target == FLOOR else D('10'))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch(REPRICE, return_value=[])
        self.m_reprice = p.start()
        self.addCleanup(p.stop)

    def test_grant_sets_fields_and_reprices(self):
        with mock.patch(PROMO_CFG, return_value={'days': 60, 'percent': D('0')}):
            self.assertTrue(vc.grant_launch_promo(self.profile, today=TODAY))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.commission_promo_percent, D('0.00'))
        self.assertEqual(self.profile.commission_promo_until, date(2027, 1, 10))
        self.assertIsNotNone(self.profile.launch_promo_granted_at)
        self.m_reprice.assert_called_once()

    def test_grant_only_once(self):
        with mock.patch(PROMO_CFG, return_value={'days': 60, 'percent': D('0')}):
            self.assertTrue(vc.grant_launch_promo(self.profile, today=TODAY))
            self.assertFalse(vc.grant_launch_promo(self.profile, today=TODAY))
        self.assertEqual(self.m_reprice.call_count, 1)

    def test_grant_off_when_days_zero(self):
        with mock.patch(PROMO_CFG, return_value={'days': 0, 'percent': D('0')}):
            self.assertFalse(vc.grant_launch_promo(self.profile, today=TODAY))
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.commission_promo_until)

    def test_only_first_approval_gets_offer(self):
        with mock.patch(PROMO_CFG, return_value={'days': 60, 'percent': D('0')}):
            self.assertFalse(vc.on_vendor_approved(self.profile, first_time=False))
            self.assertTrue(vc.on_vendor_approved(self.profile, first_time=True))

    def test_approval_survives_promo_error(self):
        with mock.patch(PROMO_CFG, side_effect=RuntimeError('boom')):
            self.assertFalse(vc.on_vendor_approved(self.profile, first_time=True))

    def test_expire_clears_promo_after_date(self):
        VendorProfile.objects.filter(pk=self.profile.pk).update(
            commission_promo_percent=D('0'), commission_promo_until=date(2026, 11, 11))
        self.assertEqual(vc.expire_promos(today=TODAY), 1)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.commission_promo_percent)
        self.assertIsNone(self.profile.commission_promo_until)
        self.m_reprice.assert_called_once()

    def test_expire_leaves_running_promo_alone(self):
        VendorProfile.objects.filter(pk=self.profile.pk).update(
            commission_promo_percent=D('0'), commission_promo_until=TODAY)
        self.assertEqual(vc.expire_promos(today=TODAY), 0)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.commission_promo_until, TODAY)
        self.m_reprice.assert_not_called()

    def test_expire_keeps_fields_when_reprice_fails(self):
        VendorProfile.objects.filter(pk=self.profile.pk).update(
            commission_promo_percent=D('0'), commission_promo_until=date(2026, 11, 11))
        self.m_reprice.return_value = ['Burger: margin policy']
        self.assertEqual(vc.expire_promos(today=TODAY), 0)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.commission_promo_until, date(2026, 11, 11))   # agli dafa dobara koshish

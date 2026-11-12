"""
Tests: homepage Pro / Loyalty cards (_club_cards) and the default-ON flags.

Run:  python manage.py test app.tests_suite.tests_club_cards -v 2

NOTE: written by reading the code, without a Django project to run it in; offers are patched.
"""
from decimal import Decimal as D
from unittest import mock

from django.test import SimpleTestCase

from app.customer import views_customer_portal as v
from app.module_config import shop_flags

PRO = 'app.customer.offers.pro_settings'
LOY = 'app.customer.offers.loyalty_settings'
WAL = 'app.customer.offers.wallet_enabled'


class FlagDefaults(SimpleTestCase):
    def test_defaults_on(self):
        self.assertTrue(shop_flags.flag_default('shop_pro_enabled'))
        self.assertTrue(shop_flags.flag_default('shop_loyalty_enabled'))


class ClubCards(SimpleTestCase):
    def test_both_on(self):
        with mock.patch(PRO, return_value={'enabled': True, 'price': D('500'), 'days': 30, 'min_order': D('0')}), \
                mock.patch(LOY, return_value={'enabled': True, 'per_100': D('1'), 'value': D('1'), 'min_redeem': 100}), \
                mock.patch(WAL, return_value=True):
            cards = v._club_cards()
        self.assertEqual([c['url'] for c in cards], ['pro_page', 'wallet_page'])
        self.assertIn('Rs 500 for 30 days', cards[0]['text'])
        self.assertIn('1 point for every Rs 100', cards[1]['text'])

    def test_pro_min_order_shown(self):
        with mock.patch(PRO, return_value={'enabled': True, 'price': D('0'), 'days': 30, 'min_order': D('800')}), \
                mock.patch(LOY, return_value={'enabled': False, 'per_100': D('1'), 'value': D('1'), 'min_redeem': 100}), \
                mock.patch(WAL, return_value=True):
            cards = v._club_cards()
        self.assertEqual(len(cards), 1)
        self.assertIn('Join for 30 days', cards[0]['text'])
        self.assertIn('over Rs 800', cards[0]['text'])

    def test_loyalty_needs_wallet(self):
        with mock.patch(PRO, return_value={'enabled': False, 'price': D('0'), 'days': 30, 'min_order': D('0')}), \
                mock.patch(LOY, return_value={'enabled': True, 'per_100': D('1'), 'value': D('1'), 'min_redeem': 100}), \
                mock.patch(WAL, return_value=False):
            self.assertEqual(v._club_cards(), [])

    def test_error_gives_empty_list(self):
        with mock.patch(PRO, side_effect=RuntimeError('db down')):
            self.assertEqual(v._club_cards(), [])

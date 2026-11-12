"""
Tests: customer referral (dost ko bulao) - code, pending, reward, fraud checks, cap, admin, UI card.

Run:  python manage.py test app.tests_suite.tests_referral -v 2

NOTE: written by reading the code, without a Django project to run it in. If a fixture line fails on a
field name, fix it in the helpers at the top - the assertions are what matter. `enabled()` and
`referral_settings()` are patched, and each order's total is patched, so no flags / products are needed.
Orders are created 'pending' and moved to 'delivered' with queryset.update() (no signal), so that every
test calls `award_for_order` itself, exactly once, when it wants to.

Hand-calculated numbers (referrer reward 100, referee reward 50, minimum first order 500, no cap unless stated):
    first delivered order 600                 -> referrer +100 ('referral'), referee +50 ('refbonus'), rewarded
    same order awarded twice                  -> still exactly 2 wallet rows (one per kind)
    order total 499.99                        -> nothing (pending);  500.00 -> rewarded
    referee already had a delivered order     -> nothing (not the FIRST delivered order)
    cap 150: first referral 100 (used 100); second 100 -> 100 + 100 = 200 > 150 -> rejected 'cap poora'
    phone not verified                        -> pending (HOLD); after verifying -> rewarded
    same phone (+92 / 0 spelling differs)     -> rejected 'Same phone number'
    admin Approve on a rejected referral      -> rewarded, same wallet credits (no fraud checks)
    earned on referrer's card                 -> 100 (only 'referral' kind; the friend's 'refbonus' is not counted)
"""
from decimal import Decimal
from unittest import mock

from django.contrib import admin as dj_admin
from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from app.customer import referrals as rf
from app.models import Customer, CustomerProfile, Referral, SaleOrder, WalletTransaction, Warehouse

D = Decimal
CFG = {'enabled': True, 'referrer_reward': D('100'), 'referee_reward': D('50'),
       'min_order': D('500'), 'monthly_cap': D('0')}


# ------------------------------------------------------------------ pure helpers (no database)
class PureHelperTests(SimpleTestCase):
    def test_normalize_code(self):
        self.assertEqual(rf.normalize_code(' abcd 2345 '), 'ABCD2345')
        for bad in ('ABCD0345', 'ABCDI345', 'ABC', 'ABCD23456', '', None):     # 0 / I / length / empty
            self.assertEqual(rf.normalize_code(bad), '', bad)

    def test_phone_key_ignores_spelling(self):
        self.assertEqual(rf.phone_key('+92 300-1234567'), '3001234567')
        self.assertEqual(rf.phone_key('0300 1234567'), '3001234567')
        self.assertEqual(rf.phone_key('123'), '')

    def test_address_key(self):
        self.assertEqual(rf.address_key('House 12, Street 4!!  Lahore'), 'house 12 street 4 lahore')
        self.assertEqual(rf.address_key('ghar'), '')        # bohat chhota: match ke liye kaafi nahi

    def test_whatsapp_url(self):
        url = rf.whatsapp_url('https://s.pk/shop/r/ABCD2345/', 'Pizza & Co', D('50'), D('500'))
        self.assertTrue(url.startswith('https://wa.me/?text='))
        self.assertNotIn(' ', url)
        self.assertNotIn('&Co', url)            # '&' encode hona chahiye
        self.assertIn('Rs.%2050', url)
        self.assertNotIn('bonus', rf.whatsapp_url('L', 'Shop', D('0'), D('500')))

    def test_month_start(self):
        m = rf.month_start()
        self.assertEqual((m.day, m.hour, m.minute), (1, 0, 0))
        self.assertLessEqual(m, timezone.now())


# ------------------------------------------------------------------ database tests
class ReferralBase(TestCase):
    def setUp(self):
        self.cfg = dict(CFG)
        self.totals = {}
        self.wh = Warehouse.objects.create(name='Main')
        self._n = 0
        patches = [
            mock.patch.object(rf, 'enabled', return_value=True),
            mock.patch.object(rf, 'referral_settings', side_effect=lambda: self.cfg),
            mock.patch.object(SaleOrder, 'total_after_discount', autospec=True,
                              side_effect=lambda order: self.totals.get(order.pk, D('600'))),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def customer(self, phone=None, verified=True, active=True, address=''):
        self._n += 1
        n = self._n
        cust = Customer.objects.create(name=f'Cust {n}', customer_code=f'C-{n:04d}',
                                       contact_number=phone or f'03{n:09d}', address=address)
        user = User.objects.create_user(f'user{n}', f'u{n}@x.com', 'pw12345!', is_active=active)
        CustomerProfile.objects.create(customer=cust, user=user, phone_verified=verified)
        return cust

    def code(self, customer):
        return rf.ensure_code(customer)

    def deliver(self, customer, total=D('600')):
        """Delivered order banao (signal ke baghair) - reward khud nahi milta jab tak award_for_order na bulayen."""
        order = SaleOrder.objects.create(customer=customer, warehouse=self.wh, order_date=timezone.now(),
                                         status='pending')
        self.totals[order.pk] = total
        SaleOrder.objects.filter(pk=order.pk).update(status='delivered')
        order.refresh_from_db()
        return order

    def refer(self, referrer, referee):
        return rf.create_pending(referee, self.code(referrer))

    def wallet(self, customer, kind):
        return WalletTransaction.objects.filter(customer=customer, kind=kind).aggregate(
            t=Sum('amount'))['t'] or D('0')


class CodeTests(ReferralBase):
    def test_codes_unique_and_well_formed(self):
        codes = [self.code(self.customer()) for _ in range(40)]
        self.assertEqual(len(set(codes)), 40)
        for c in codes:
            self.assertRegex(c, rf.CODE_RE.pattern)

    def test_ensure_code_is_stable_and_fills_missing(self):
        cust = self.customer()
        first = self.code(cust)
        self.assertEqual(self.code(cust), first)
        CustomerProfile.objects.filter(customer=cust).update(referral_code=None)    # purana customer
        again = self.code(cust)
        self.assertTrue(rf.CODE_RE.match(again))

    def test_find_referrer(self):
        a = self.customer()
        self.assertEqual(rf.find_referrer(self.code(a).lower()), a)
        self.assertIsNone(rf.find_referrer('ZZZZZZZZ'))
        self.assertIsNone(rf.find_referrer('bad'))


class CreatePendingTests(ReferralBase):
    def test_valid_referral_is_pending(self):
        a, b = self.customer(), self.customer()
        ref = self.refer(a, b)
        self.assertEqual((ref.referrer, ref.referee, ref.status), (a, b, 'pending'))

    def test_self_referral_ignored(self):
        a = self.customer()
        self.assertIsNone(rf.create_pending(a, self.code(a)))
        self.assertEqual(Referral.objects.count(), 0)

    def test_unknown_code_ignored(self):
        self.assertIsNone(rf.create_pending(self.customer(), 'ZZZZZZZZ'))

    def test_second_referral_for_same_friend_ignored(self):
        a, b, c = self.customer(), self.customer(), self.customer()
        first = self.refer(a, c)
        self.assertIsNone(self.refer(b, c))
        self.assertEqual(Referral.objects.get().pk, first.pk)

    def test_flag_off_creates_nothing(self):
        a, b = self.customer(), self.customer()
        with mock.patch.object(rf, 'enabled', return_value=False):
            self.assertIsNone(rf.create_pending(b, self.code(a)))


class RewardTests(ReferralBase):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.customer(), self.customer()
        self.ref = self.refer(self.a, self.b)

    def test_both_sides_get_wallet_credit(self):
        order = self.deliver(self.b, D('600'))
        got = rf.award_for_order(order)
        self.assertEqual(got.status, 'rewarded')
        self.assertEqual(self.wallet(self.a, 'referral'), D('100.00'))
        self.assertEqual(self.wallet(self.b, 'refbonus'), D('50.00'))
        self.ref.refresh_from_db()
        self.assertEqual((self.ref.referrer_amount, self.ref.referee_amount, self.ref.reward_order_id),
                         (D('100.00'), D('50.00'), order.pk))
        self.assertIsNotNone(self.ref.rewarded_at)

    def test_no_double_reward(self):
        order = self.deliver(self.b)
        rf.award_for_order(order)
        self.assertIsNone(rf.award_for_order(order))              # status ab 'rewarded', dobara kuch nahi
        self.assertEqual(WalletTransaction.objects.filter(kind__in=('referral', 'refbonus')).count(), 2)
        later = self.deliver(self.b)
        self.assertIsNone(rf.award_for_order(later))
        self.assertEqual(WalletTransaction.objects.filter(kind__in=('referral', 'refbonus')).count(), 2)

    def test_not_rewarded_until_delivered(self):
        pending = SaleOrder.objects.create(customer=self.b, warehouse=self.wh, order_date=timezone.now(),
                                           status='pending')
        self.assertIsNone(rf.award_for_order(pending))
        self.assertEqual(WalletTransaction.objects.count(), 0)

    def test_minimum_amount(self):
        low = self.deliver(self.b, D('499.99'))
        self.assertIsNone(rf.award_for_order(low))
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.status, 'pending')
        # pehla delivered order ab 'low' hai, isliye agla order bhi reward nahi deta (sirf PEHLA delivered order)
        self.assertIsNone(rf.award_for_order(self.deliver(self.b, D('900'))))

    def test_exact_minimum_is_enough(self):
        self.assertIsNotNone(rf.award_for_order(self.deliver(self.b, D('500.00'))))

    def test_only_first_delivered_order(self):
        old = self.deliver(self.b, D('300'))
        self.assertIsNone(rf.award_for_order(old))
        self.assertIsNone(rf.award_for_order(self.deliver(self.b, D('900'))))
        self.assertEqual(WalletTransaction.objects.count(), 0)

    def test_zero_rewards_do_nothing(self):
        self.cfg.update(referrer_reward=D('0'), referee_reward=D('0'))
        self.assertIsNone(rf.award_for_order(self.deliver(self.b)))

    def test_only_one_side_reward(self):
        self.cfg.update(referee_reward=D('0'))
        rf.award_for_order(self.deliver(self.b))
        self.assertEqual(self.wallet(self.a, 'referral'), D('100.00'))
        self.assertEqual(WalletTransaction.objects.filter(kind='refbonus').count(), 0)

    def test_flag_off_no_reward(self):
        order = self.deliver(self.b)
        with mock.patch.object(rf, 'enabled', return_value=False):
            self.assertIsNone(rf.award_for_order(order))


class FraudTests(ReferralBase):
    def test_unverified_phone_holds_then_rewards(self):
        a, b = self.customer(), self.customer(verified=False)
        ref = self.refer(a, b)
        order = self.deliver(b)
        self.assertIsNone(rf.award_for_order(order))
        ref.refresh_from_db()
        self.assertEqual(ref.status, 'pending')                   # HOLD: rejected nahi
        CustomerProfile.objects.filter(customer=b).update(phone_verified=True)
        self.assertEqual(rf.award_for_order(order).status, 'rewarded')

    def test_same_phone_rejected(self):
        a, b = self.customer(phone='+92 300 1234567'), self.customer(phone='0300-1234567')
        ref = self.refer(a, b)
        self.assertIsNone(rf.award_for_order(self.deliver(b)))
        ref.refresh_from_db()
        self.assertEqual((ref.status, ref.reject_reason), ('rejected', 'Same phone number'))
        self.assertEqual(WalletTransaction.objects.count(), 0)

    def test_same_address_rejected(self):
        a = self.customer(address='House 12, Street 4, Gulberg, Lahore')
        b = self.customer(address='house 12 street 4 gulberg lahore')
        ref = self.refer(a, b)
        self.assertIsNone(rf.award_for_order(self.deliver(b)))
        ref.refresh_from_db()
        self.assertEqual((ref.status, ref.reject_reason), ('rejected', 'Same address'))

    def test_same_device_rejected(self):
        a, b, c = self.customer(), self.customer(), self.customer()
        Referral.objects.create(referrer=a, referee=b, device_hash='h1')
        ref = Referral.objects.create(referrer=a, referee=c, device_hash='h1')
        self.assertIsNone(rf.award_for_order(self.deliver(c)))
        ref.refresh_from_db()
        self.assertEqual((ref.status, ref.reject_reason), ('rejected', 'Same device (IP + browser)'))

    def test_inactive_referrer_rejected(self):
        a, b = self.customer(active=False), self.customer()
        ref = self.refer(a, b)
        self.assertIsNone(rf.award_for_order(self.deliver(b)))
        ref.refresh_from_db()
        self.assertEqual((ref.status, ref.reject_reason), ('rejected', 'Referrer ka account active nahi'))

    def test_monthly_cap(self):
        self.cfg['monthly_cap'] = D('150')
        a, b, c = self.customer(), self.customer(), self.customer()
        r1, r2 = self.refer(a, b), self.refer(a, c)
        self.assertEqual(rf.award_for_order(self.deliver(b)).status, 'rewarded')      # used 100
        self.assertIsNone(rf.award_for_order(self.deliver(c)))                        # 100 + 100 > 150
        r2.refresh_from_db()
        self.assertEqual((r2.status, r2.reject_reason), ('rejected', 'Referrer ka mahine ka cap poora'))
        self.assertEqual(self.wallet(a, 'referral'), D('100.00'))

    def test_cap_zero_means_no_limit(self):
        self.cfg['monthly_cap'] = D('0')
        a = self.customer()
        for _ in range(3):
            friend = self.customer()
            self.refer(a, friend)
            self.assertIsNotNone(rf.award_for_order(self.deliver(friend)))
        self.assertEqual(self.wallet(a, 'referral'), D('300.00'))


class ManualApproveTests(ReferralBase):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.customer(phone='0300-1234567'), self.customer(phone='+92 300 1234567')
        self.ref = self.refer(self.a, self.b)
        self.order = self.deliver(self.b)
        rf.award_for_order(self.order)                              # same phone -> rejected
        self.ref.refresh_from_db()
        assert self.ref.status == 'rejected'

    def test_admin_override_rewards(self):
        got = rf.manual_approve(self.ref.pk)
        self.assertEqual((got.status, got.reject_reason, got.reward_order_id), ('rewarded', '', self.order.pk))
        self.assertEqual(self.wallet(self.a, 'referral'), D('100.00'))
        self.assertEqual(self.wallet(self.b, 'refbonus'), D('50.00'))

    def test_needs_a_delivered_order(self):
        x, y = self.customer(), self.customer()
        ref = self.refer(x, y)
        with self.assertRaises(rf.ReferralActionError):
            rf.manual_approve(ref.pk)

    def test_cannot_approve_twice(self):
        rf.manual_approve(self.ref.pk)
        with self.assertRaises(rf.ReferralActionError):
            rf.manual_approve(self.ref.pk)
        self.assertEqual(WalletTransaction.objects.filter(kind__in=('referral', 'refbonus')).count(), 2)

    def test_blocked_when_flag_off(self):
        with mock.patch.object(rf, 'enabled', return_value=False):
            with self.assertRaises(rf.ReferralActionError):
                rf.manual_approve(self.ref.pk)


class AdminAndCardTests(ReferralBase):
    def setUp(self):
        super().setUp()
        self.ma = dj_admin.site._registry[Referral]
        self.a, self.b = self.customer(), self.customer()
        self.ref = self.refer(self.a, self.b)

    def test_reject_action_touches_only_pending(self):
        done = Referral.objects.create(referrer=self.a, referee=self.customer(), status='rewarded')
        with mock.patch.object(self.ma, 'message_user'):
            self.ma.reject_selected(None, Referral.objects.all())
        self.ref.refresh_from_db()
        done.refresh_from_db()
        self.assertEqual((self.ref.status, self.ref.reject_reason), ('rejected', 'Admin ne reject kiya'))
        self.assertEqual(done.status, 'rewarded')

    def test_approve_action_rewards_when_possible(self):
        self.deliver(self.b)
        with mock.patch.object(self.ma, 'message_user') as msg:
            self.ma.approve_selected(None, Referral.objects.all())
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.status, 'rewarded')
        self.assertTrue(msg.called)

    def test_approve_action_reports_missing_order(self):
        with mock.patch.object(self.ma, 'message_user') as msg:
            self.ma.approve_selected(None, Referral.objects.all())
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.status, 'pending')
        self.assertIn('delivered', str(msg.call_args_list))

    def test_admin_cannot_add_or_delete(self):
        self.assertFalse(self.ma.has_add_permission(None))
        self.assertFalse(self.ma.has_delete_permission(None))

    def test_card_numbers(self):
        request = RequestFactory().get('/shop/account/')
        card = rf.referral_card(request, self.a, 'Shop')
        self.assertEqual((card['invited'], card['pending'], card['rewarded'], card['earned']), (1, 1, 0, D('0.00')))
        self.assertIn(f'/shop/r/{card["code"]}/', card['link'])
        rf.award_for_order(self.deliver(self.b))
        card = rf.referral_card(request, self.a, 'Shop')
        self.assertEqual((card['invited'], card['pending'], card['rewarded'], card['earned']), (1, 0, 1, D('100.00')))
        # dost ke card par 'earned' 0: uska bonus 'refbonus' hai, 'referral' nahi
        self.assertEqual(rf.referral_card(request, self.b, 'Shop')['earned'], D('0.00'))

    def test_card_hidden_when_off(self):
        request = RequestFactory().get('/')
        with mock.patch.object(rf, 'enabled', return_value=False):
            self.assertIsNone(rf.referral_card(request, self.a, 'Shop'))


class PhoneVerifiedLaterTests(ReferralBase):
    """Phone delivery ke BAAD verify ho to ruka hua reward ab mil jata hai."""

    def setUp(self):
        super().setUp()
        self.a, self.b = self.customer(), self.customer(verified=False)
        self.ref = self.refer(self.a, self.b)

    def test_reward_released_when_phone_verified(self):
        order = self.deliver(self.b)
        self.assertIsNone(rf.award_for_order(order))                    # phone verify nahi: ruka
        CustomerProfile.objects.filter(customer=self.b).update(phone_verified=True)
        got = rf.award_on_phone_verified(self.b)
        self.assertEqual((got.status, got.reward_order_id), ('rewarded', order.pk))
        self.assertEqual(self.wallet(self.a, 'referral'), D('100.00'))
        self.assertEqual(self.wallet(self.b, 'refbonus'), D('50.00'))

    def test_second_call_pays_nothing_more(self):
        self.deliver(self.b)
        CustomerProfile.objects.filter(customer=self.b).update(phone_verified=True)
        rf.award_on_phone_verified(self.b)
        self.assertIsNone(rf.award_on_phone_verified(self.b))
        self.assertEqual(WalletTransaction.objects.filter(kind__in=('referral', 'refbonus')).count(), 2)

    def test_nothing_without_delivered_order(self):
        CustomerProfile.objects.filter(customer=self.b).update(phone_verified=True)
        self.assertIsNone(rf.award_on_phone_verified(self.b))
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.status, 'pending')

    def test_minimum_still_applies(self):
        self.deliver(self.b, D('499.99'))
        CustomerProfile.objects.filter(customer=self.b).update(phone_verified=True)
        self.assertIsNone(rf.award_on_phone_verified(self.b))

    def test_customer_without_referral_is_ignored(self):
        lone = self.customer()
        self.deliver(lone)
        self.assertIsNone(rf.award_on_phone_verified(lone))
        self.assertIsNone(rf.award_on_phone_verified(None))

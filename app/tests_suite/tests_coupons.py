"""
Tests: coupons / promo codes.

Run:  python manage.py test app.tests_suite.tests_coupons -v 2

NOTE: written by reading the code, without a Django project to run it in (settings.py was not in
the zip). If a fixture line fails on a field name, fix it in setUp - the assertions are what matter.

Hand-calculated numbers:
    20% of 1000, max 150      -> 150.00   (cap)
    20% of 500,  max 150      -> 100.00
    fixed 80 on subtotal 50   -> 50.00    (never more than the subtotal)
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from app.customer import coupons as logic
from app.models import Coupon, Customer, SaleOrder, Warehouse

D = Decimal


class CouponMathTests(TestCase):
    def test_percent_with_cap(self):
        c = Coupon(code='A1', discount_type='percent', value=D('20'), max_discount=D('150'))
        self.assertEqual(c.compute(D('1000')), D('150.00'))
        self.assertEqual(c.compute(D('500')), D('100.00'))

    def test_fixed_never_exceeds_subtotal(self):
        c = Coupon(code='A2', discount_type='fixed', value=D('80'))
        self.assertEqual(c.compute(D('50')), D('50.00'))
        self.assertEqual(c.compute(D('200')), D('80.00'))

    def test_code_saved_uppercase_no_spaces(self):
        c = Coupon.objects.create(code=' wel come20 ', discount_type='percent', value=D('20'))
        self.assertEqual(c.code, 'WELCOME20')

    def test_badge_text(self):
        self.assertEqual(Coupon(code='B1', discount_type='percent', value=D('20')).badge, '20% off')
        self.assertEqual(Coupon(code='B2', discount_type='fixed', value=D('5.50')).badge, '5.50 off')
        self.assertEqual(Coupon(code='B3', title='Free dessert', value=D('1')).badge, 'Free dessert')


class CouponValidateTests(TestCase):
    def setUp(self):
        self.cust = Customer.objects.create(name='Ali', customer_code='C-001')
        self.other = Customer.objects.create(name='Sara', customer_code='C-002')
        self.wh = Warehouse.objects.create(name='Main')

    def _coupon(self, **kw):
        base = dict(code='SAVE10', discount_type='percent', value=D('10'))
        base.update(kw)
        return Coupon.objects.create(**base)

    def _use(self, coupon, customer, status='pending'):
        o = SaleOrder.objects.create(customer=customer, warehouse=self.wh, order_date=timezone.now(), status=status)
        logic.record_redemption(o, coupon, customer, D('10'))
        return o

    def test_valid_coupon(self):
        self._coupon()
        coupon, discount, err = logic.validate('save10', self.cust, 0, D('500'))
        self.assertIsNone(err)
        self.assertEqual(discount, D('50.00'))

    def test_wrong_code(self):
        self.assertEqual(logic.validate('NOPE', self.cust, 0, D('500'))[2], 'Yeh coupon code sahi nahi hai.')

    def test_needs_login(self):
        self._coupon()
        self.assertIn('login', logic.validate('SAVE10', None, 0, D('500'))[2])

    def test_min_order(self):
        self._coupon(min_order=D('300'))
        self.assertIsNotNone(logic.validate('SAVE10', self.cust, 0, D('200'))[2])
        self.assertIsNone(logic.validate('SAVE10', self.cust, 0, D('300'))[2])

    def test_expired_and_scheduled_and_off(self):
        today = timezone.localdate()
        self._coupon(code='OLD', ends_on=today - timedelta(days=1))
        self._coupon(code='SOON', starts_on=today + timedelta(days=1))
        self._coupon(code='OFF', is_active=False)
        for code in ('OLD', 'SOON', 'OFF'):
            self.assertIsNotNone(logic.validate(code, self.cust, 0, D('500'))[2], code)

    def test_per_customer_limit_and_cancelled_order_frees_use(self):
        c = self._coupon(per_customer_limit=1)
        o = self._use(c, self.cust)
        self.assertIsNotNone(logic.validate('SAVE10', self.cust, 0, D('500'))[2])    # already used
        self.assertIsNone(logic.validate('SAVE10', self.other, 0, D('500'))[2])      # someone else can
        o.status = 'cancelled'
        o.save()
        self.assertIsNone(logic.validate('SAVE10', self.cust, 0, D('500'))[2])       # cancelled order frees the use

    def test_total_usage_limit(self):
        c = self._coupon(usage_limit=1, per_customer_limit=0)
        self._use(c, self.cust)
        self.assertEqual(c.status, 'used_up')
        self.assertIsNotNone(logic.validate('SAVE10', self.other, 0, D('500'))[2])

    def test_first_order_only(self):
        self._coupon(first_order_only=True, per_customer_limit=0)
        self.assertIsNone(logic.validate('SAVE10', self.cust, 0, D('500'))[2])
        SaleOrder.objects.create(customer=self.cust, warehouse=self.wh, order_date=timezone.now(), status='pending')
        self.assertIsNotNone(logic.validate('SAVE10', self.cust, 0, D('500'))[2])

    def test_redemption_is_recorded_once_per_order(self):
        c = self._coupon(per_customer_limit=0)
        o = self._use(c, self.cust)
        logic.record_redemption(o, c, self.cust, D('10'))        # second call must not create a duplicate
        self.assertEqual(c.redemptions.count(), 1)

"""
Coupons / offers - customer side logic (cart + checkout + store cards).

- Customer cart/checkout par code likhta hai -> session['coupon_code'] mein rehta hai.
- Discount SaleOrder.discount_value mein jata hai; CouponRedemption order ke sath banta hai.
- Har baar total nikalte waqt coupon dobara check hota hai (store badla, subtotal ghata, expire...).
"""
from decimal import Decimal

from django.db.models import Q

SESSION_KEY = 'coupon_code'
ZERO = Decimal('0.00')


def _fmt(n):
    return f"{Decimal(n):,.0f}"


def validate(code, customer, vendor_id, subtotal, lock=False):
    """
    -> (coupon, discount, error).  Theek ho to (coupon, discount, None), warna (None, 0, 'wajah').
    vendor_id: cart ka store (0 = shop ka apna maal). lock=True sirf transaction ke andar.
    """
    from ..models import Coupon, SaleOrder
    code = (code or '').strip().upper().replace(' ', '')
    if not code:
        return None, ZERO, None
    qs = Coupon.objects.select_for_update() if lock else Coupon.objects
    coupon = qs.filter(code=code).select_related('store').first()
    if coupon is None:
        return None, ZERO, 'This coupon code is not valid.'
    st = coupon.status
    if st == 'off':
        return None, ZERO, 'This coupon is not active right now.'
    if st == 'scheduled':
        return None, ZERO, 'This coupon has not started yet.'
    if st == 'expired':
        return None, ZERO, 'Yeh coupon expire ho chuka hai.'
    if st == 'used_up':
        return None, ZERO, 'Yeh coupon ki hadd poori ho gayi.'
    if coupon.store_id and coupon.store.vendor_id != int(vendor_id or 0):
        return None, ZERO, f'Yeh coupon sirf {coupon.store.business_name} ke liye hai.'
    subtotal = Decimal(subtotal or 0)
    if subtotal < Decimal(coupon.min_order or 0):
        return None, ZERO, f'Is coupon ke liye kam az kam {_fmt(coupon.min_order)} ka order chahiye.'
    if customer is None:
        return None, ZERO, 'Coupon use karne ke liye pehle login karein.'
    mine = coupon.redemptions.filter(customer=customer).exclude(order__status='cancelled')
    if coupon.per_customer_limit and mine.count() >= coupon.per_customer_limit:
        return None, ZERO, 'You have already used this coupon.'
    if coupon.first_order_only and SaleOrder.objects.filter(customer=customer).exclude(status='cancelled').exists():
        return None, ZERO, 'Yeh coupon sirf pehle order par chalta hai.'
    discount = coupon.compute(subtotal)
    if discount <= 0:
        return None, ZERO, 'Is order par yeh coupon discount nahi deta.'
    return coupon, discount, None


def cart_coupon(code, customer, vendor_id, subtotal):
    """calculate_cart_data ke liye: {'coupon', 'discount', 'error', 'code'}. Flag OFF ho to koi discount nahi."""
    from ..shop_flags import shop_flag
    out = {'coupon': None, 'discount': ZERO, 'error': None, 'code': (code or '').strip().upper()}
    if not out['code'] or not shop_flag('shop_coupons_enabled'):
        return out
    coupon, discount, error = validate(code, customer, vendor_id, subtotal)
    out.update({'coupon': coupon, 'discount': discount, 'error': error})
    return out


def record_redemption(order, coupon, customer, amount):
    """Order ban gaya -> coupon ka istemal likh do (OneToOne: dobara nahi banta)."""
    from ..models import CouponRedemption
    if coupon is None or not amount or Decimal(amount) <= 0:
        return None
    obj, _ = CouponRedemption.objects.get_or_create(
        order=order, defaults={'coupon': coupon, 'customer': customer, 'amount': amount})
    return obj


def store_offers():
    """{vendor_id: Coupon} - store card/page par dikhane wale live offers (har store ka behtareen ek)."""
    from ..models import Coupon
    from ..shop_flags import shop_flag
    if not shop_flag('shop_coupons_enabled'):
        return {}
    out = {}
    qs = (Coupon.live().filter(show_on_store=True, store__isnull=False, store__is_approved=True)
          .select_related('store').order_by('-created_at'))
    for c in qs:
        if c.status != 'live':
            continue
        # percent coupon pehle, phir bara value
        cur = out.get(c.store.vendor_id)
        rank = (c.discount_type == 'percent', c.value)
        if cur is None or rank > (cur.discount_type == 'percent', cur.value):
            out[c.store.vendor_id] = c
    return out

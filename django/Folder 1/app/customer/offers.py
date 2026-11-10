"""Offers - coupon + Pro (free delivery) + wallet + cashback ka sara hisaab ek jagah.

Cart / checkout / place_order sab isi se total nikalte hain, taake customer ko jo dikhe wahi order mein bane.

Tarteeb:  items subtotal  -  coupon discount  +  delivery (Pro ho to maaf)  =  total
          total  -  wallet  =  customer ko cash / online dena
"""
import logging
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone

from ..shop_flags import shop_flag
from . import coupons as coupon_logic
from . import store_orders

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')
CENT = Decimal('0.01')
WALLET_SESSION_KEY = 'use_wallet'
DONE_STATUSES = ('delivered', 'invoiced', 'partially_delivered')


# ---------------------------------------------------------------- settings
def setting_decimal(name, default='0'):
    """Admin ki Settings > Shop se ek raqam (SystemSetting). Galat ya khali ho to default."""
    from ..models import SystemSetting
    raw = SystemSetting.objects.filter(setting_key=name).values_list('setting_value', flat=True).first()
    try:
        return Decimal(str(raw).strip()) if raw not in (None, '') else Decimal(default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def pro_settings():
    return {
        'enabled': shop_flag('shop_pro_enabled'),
        'price': setting_decimal('pro_price', '0'),
        'days': int(setting_decimal('pro_days', '30')),
        'min_order': setting_decimal('pro_min_order', '0'),
    }


# ---------------------------------------------------------------- wallet
def wallet_enabled():
    return shop_flag('shop_wallet_enabled')


def wallet_balance(customer):
    if customer is None:
        return ZERO
    from ..models import WalletTransaction
    total = WalletTransaction.objects.filter(customer=customer).aggregate(t=Sum('amount'))['t']
    return Decimal(total or 0).quantize(CENT)


def cashback_for(order):
    """Is order par kitna cashback banta hai (items - coupon discount ka %, max tak)."""
    pct = setting_decimal('cashback_percent', '0')
    if pct <= 0 or not shop_flag('shop_wallet_enabled'):
        return ZERO
    base = Decimal(order.total_after_discount() or 0)
    amount = (base * pct / Decimal('100')).quantize(CENT, ROUND_HALF_UP)
    cap = setting_decimal('cashback_max', '0')
    if cap > 0:
        amount = min(amount, cap)
    return max(amount, ZERO)


def award_cashback(order):
    """Delivered order par cashback wallet mein (ek order par sirf ek dafa)."""
    from ..models import WalletTransaction
    amount = cashback_for(order)
    if amount <= 0 or not order.customer_id:
        return None
    try:
        obj, _ = WalletTransaction.objects.get_or_create(
            order=order, kind='cashback',
            defaults={'customer_id': order.customer_id, 'amount': amount,
                      'note': f'Cashback: order #{order.order_no}'})
        return obj
    except IntegrityError:          # do jagah se ek saath chala: ek hi rahega
        return None


def refund_wallet(order):
    """Cancel order par wallet se kata hua paisa wapas (ek dafa)."""
    from ..models import WalletTransaction
    paid = Decimal(order.wallet_paid or 0)
    if paid <= 0 or not order.customer_id:
        return None
    if not WalletTransaction.objects.filter(order=order, kind='spend').exists():
        return None
    try:
        obj, _ = WalletTransaction.objects.get_or_create(
            order=order, kind='refund',
            defaults={'customer_id': order.customer_id, 'amount': paid,
                      'note': f'Wapas: order #{order.order_no} cancel'})
        return obj
    except IntegrityError:
        return None


# ---------------------------------------------------------------- loyalty points
def loyalty_settings():
    return {
        'enabled': shop_flag('shop_loyalty_enabled'),
        'per_100': setting_decimal('loyalty_points_per_100', '1'),
        'value': setting_decimal('loyalty_point_value', '1'),
        'min_redeem': max(int(setting_decimal('loyalty_min_redeem', '100')), 1),
    }


def points_from_amount(amount, per_100):
    """Rs amount par kitne points (poore points, baqi chhor diye jate hain)."""
    amount, per_100 = Decimal(amount or 0), Decimal(per_100 or 0)
    if amount <= 0 or per_100 <= 0:
        return 0
    return int((amount / Decimal('100') * per_100).to_integral_value(rounding=ROUND_DOWN))


def points_balance(customer):
    if customer is None:
        return 0
    from ..models import LoyaltyTransaction
    return int(LoyaltyTransaction.objects.filter(customer=customer).aggregate(t=Sum('points'))['t'] or 0)


def points_for(order):
    cfg = loyalty_settings()
    if not cfg['enabled']:
        return 0
    return points_from_amount(order.total_after_discount(), cfg['per_100'])


def award_points(order):
    """Delivered order par loyalty points (ek order par sirf ek dafa)."""
    from ..models import LoyaltyTransaction
    pts = points_for(order)
    if pts <= 0 or not order.customer_id:
        return None
    try:
        obj, _ = LoyaltyTransaction.objects.get_or_create(
            order=order, kind='earn',
            defaults={'customer_id': order.customer_id, 'points': pts, 'note': f'Order #{order.order_no}'})
        return obj
    except IntegrityError:
        return None


def redeem_points(customer, points):
    """Points ko wallet credit mein badlo. -> (ok, message). Poora kaam ek transaction mein, customer row lock ke sath."""
    from django.db import transaction
    from ..models import Customer, LoyaltyTransaction, WalletTransaction
    cfg = loyalty_settings()
    if not (cfg['enabled'] and wallet_enabled()):
        return False, 'Points abhi convert nahi ho sakte.'
    try:
        points = int(points)
    except (TypeError, ValueError):
        return False, 'Points sahi likhein.'
    if points < cfg['min_redeem']:
        return False, f"Kam az kam {cfg['min_redeem']} points convert ho sakte hain."
    credit = (Decimal(points) * cfg['value']).quantize(CENT, ROUND_HALF_UP)
    if credit <= 0:
        return False, 'Abhi points ki koi value set nahi.'
    with transaction.atomic():
        Customer.objects.select_for_update().filter(pk=customer.pk).first()
        if points > points_balance(customer):
            return False, 'Itne points nahi hain.'
        LoyaltyTransaction.objects.create(customer=customer, points=-points, kind='redeem',
                                          note=f'Wallet credit Rs. {credit}')
        WalletTransaction.objects.create(customer=customer, amount=credit, kind='points',
                                         note=f'{points} points')
    return True, f'{points} points se Rs. {credit:,.0f} wallet mein aa gaye.'


def sync_status(order):
    """Order ki halat ke mutabiq wallet ka kaam: delivered -> cashback, cancelled -> wapas.
    Signal aur admin ki bulk status tabdeeli (queryset.update, jis par signal nahi chalta) dono yahi bulate hain."""
    if order.status in DONE_STATUSES:
        award_points(order)
        return award_cashback(order)
    if order.status == 'cancelled':
        return refund_wallet(order)
    return None


# ---------------------------------------------------------------- pro
def active_pro(customer):
    if customer is None or not shop_flag('shop_pro_enabled'):
        return None
    from ..models import ProMembership
    return (ProMembership.objects.filter(customer=customer, status='active', ends_on__gte=timezone.localdate())
            .order_by('-ends_on').first())


# ---------------------------------------------------------------- summary
def prepare(cart, cart_data, customer, session, lock=False):
    """
    Cart ka poora hisaab: coupon, Pro delivery, wallet.  lock=True sirf transaction.atomic ke andar
    (customer row aur coupon row lock hoti hai, taake wallet / coupon do dafa kharch na ho).
    """
    if lock and customer is not None:
        from ..models import Customer
        Customer.objects.select_for_update().filter(pk=customer.pk).first()

    subtotal = Decimal(str(cart_data.get('subtotal') or 0))
    delivery = Decimal(str(cart_data.get('delivery_charges') or 0))
    out = {
        'subtotal': subtotal, 'delivery_original': delivery, 'delivery': delivery,
        'coupon': None, 'coupon_code': '', 'coupon_error': None, 'discount': ZERO,
        'pro_enabled': False, 'pro_active': False, 'pro_waived': ZERO, 'pro_hint': '',
        'wallet_on': False, 'wallet_balance': ZERO, 'use_wallet': False, 'wallet_used': ZERO,
    }

    # ---- coupon
    code = (session.get(coupon_logic.SESSION_KEY) or '').strip().upper()
    out['coupon_code'] = code
    if code and shop_flag('shop_coupons_enabled'):
        vendor_id = store_orders.cart_store_id(cart) or 0
        coupon, discount, error = coupon_logic.validate(code, customer, vendor_id, subtotal, lock=lock)
        out.update({'coupon': coupon, 'discount': discount, 'coupon_error': error})

    # ---- Pro: delivery maaf
    pro = pro_settings()
    out['pro_enabled'] = pro['enabled']
    if pro['enabled']:
        member = active_pro(customer)
        out['pro_active'] = member is not None
        if delivery > 0:
            if member and subtotal >= pro['min_order']:
                out['pro_waived'] = delivery
                delivery = ZERO
            elif member:
                out['pro_hint'] = (f"Pro: Rs. {pro['min_order'] - subtotal:,.0f} ka maal aur add karein, "
                                   f"delivery free ho jayegi.")
            else:
                out['pro_hint'] = 'Pro member banein: free delivery.'
    out['delivery'] = delivery

    # ---- total + wallet
    total = max(subtotal - out['discount'] + delivery, ZERO)
    out['total'] = total
    if wallet_enabled() and customer is not None:
        out['wallet_on'] = True
        balance = wallet_balance(customer)
        out['wallet_balance'] = balance
        want = bool(session.get(WALLET_SESSION_KEY))
        out['use_wallet'] = want and balance > 0
        if out['use_wallet'] and total > 0:
            out['wallet_used'] = min(balance, total).quantize(CENT)
    out['to_pay'] = (total - out['wallet_used']).quantize(CENT)
    cfg_l = loyalty_settings()
    out['points_est'] = (points_from_amount(max(subtotal - out['discount'], ZERO), cfg_l['per_100'])
                         if cfg_l['enabled'] and customer is not None else 0)
    return out


def finalize(order, summary, customer, session):
    """Order ban gaya: coupon ka istemal likho, wallet se paisa kato, session saaf karo."""
    from ..models import WalletTransaction
    if summary.get('coupon') and summary['discount'] > 0:
        coupon_logic.record_redemption(order, summary['coupon'], customer, summary['discount'])
    if summary.get('wallet_used', ZERO) > 0:
        WalletTransaction.objects.create(
            customer=customer, amount=-summary['wallet_used'], kind='spend', order=order,
            note=f'Order #{order.order_no}')
    session.pop(coupon_logic.SESSION_KEY, None)
    session.pop(WALLET_SESSION_KEY, None)
    try:
        session.modified = True
    except Exception:
        pass


def order_fields(summary):
    """SaleOrder.objects.create(...) mein lagane wali offers ki fields."""
    return {
        'discount_value': summary['discount'],
        'wallet_paid': summary['wallet_used'],
        'pro_delivery_waived': summary['pro_waived'],
    }

"""
Vendor ki apni deals: Buy 1 Get 1 Free, Combo, Flash sale.

- Deal cart / checkout mein discount ki tarah lagti hai (coupon se pehle), isi liye customer ko jo dikhe wahi order mein banta hai.
- Discount vendor ke hisaab se katta hai: OrderDeal mein likha jata hai aur vendor_earnings ki payable se kam hota hai.
- Ek unit par ek hi deal lagti hai (pehle Combo, phir Buy 1 Get 1, phir Flash).
- Flash sale / deal ka waqt khatam hote hi khud band (cron ki zaroorat nahi).
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from ..shop_flags import shop_flag

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')
CENT = Decimal('0.01')
MAX_ACTIVE_PER_VENDOR = 10
MAX_FLASH_PERCENT = Decimal('90')
KIND_ORDER = ('combo', 'bogo', 'flash')


def deals_enabled():
    return shop_flag('vendor_deals_enabled')


def active_deals(vendor_id, now=None):
    """Is vendor ki abhi chalti hui deals (items ke sath)."""
    from ..models import StoreDeal
    if not vendor_id or not deals_enabled():
        return []
    now = now or timezone.now()
    return list(StoreDeal.objects.filter(profile__vendor_id=vendor_id, is_active=True, starts_at__lte=now)
                .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
                .prefetch_related('items__product'))


def _q(value):
    return Decimal(value).quantize(CENT, ROUND_HALF_UP)


def compute(cart, vendor_id, now=None):
    """Cart par lagne wali deals. -> {'total': Decimal, 'lines': [{'deal', 'title', 'amount'}]}"""
    empty = {'total': ZERO, 'lines': []}
    try:
        deals = active_deals(vendor_id, now)
        if not deals or not cart:
            return empty
        pools = {}                                   # product_id -> har unit ki price (chhoti se bari)
        for item in cart.values():
            try:
                pid = int(item.get('product_id') or 0)
                qty = int(item.get('quantity') or 0)
                price = Decimal(str(item.get('price') or 0))
            except (TypeError, ValueError, ArithmeticError):
                continue
            if pid and qty > 0 and price > 0:
                pools.setdefault(pid, []).extend([price] * qty)
        for units in pools.values():
            units.sort()
        if not pools:
            return empty
        return _apply(deals, pools)
    except Exception:           # deal ki kisi galti se checkout kabhi na rukey
        logger.exception('Deals compute error')
        return empty


def _apply(deals, pools):
    lines = []
    ordered = []
    for kind in KIND_ORDER:
        group = [d for d in deals if d.kind == kind]
        if kind == 'flash':
            group.sort(key=lambda d: -(d.percent or 0))     # customer ke liye sab se achhi pehle
        else:
            group.sort(key=lambda d: d.pk)
        ordered += group

    for deal in ordered:
        items = [(it.product_id, max(int(it.qty or 1), 1)) for it in deal.items.all()]
        if not items:
            continue
        amount = ZERO
        if deal.kind == 'combo' and deal.combo_price and len(items) >= 2:
            while all(len(pools.get(pid, [])) >= q for pid, q in items):
                taken = sum((sum(pools[pid][-q:]) for pid, q in items), ZERO)
                saving = taken - Decimal(deal.combo_price)
                if saving <= 0:
                    break
                for pid, q in items:
                    del pools[pid][-q:]
                amount += saving
        elif deal.kind == 'bogo':
            pid = items[0][0]
            units = pools.get(pid, [])
            free = len(units) // 2
            if free:
                amount = sum(units[:free], ZERO)                     # sab se sasti unit free
                pools[pid] = units[-1:] if len(units) % 2 else []    # jodi poori ho chuki; bacha hua ek unit aage
        elif deal.kind == 'flash' and deal.percent and 0 < deal.percent <= MAX_FLASH_PERCENT:
            for pid, _qty in items:
                units = pools.get(pid, [])
                if units:
                    amount += sum(units, ZERO) * Decimal(deal.percent) / Decimal('100')
                    pools[pid] = []
        amount = _q(amount)
        if amount > 0:
            lines.append({'deal': deal, 'title': deal.title, 'amount': amount})
    return {'total': sum((l['amount'] for l in lines), ZERO), 'lines': lines}


def record(order, summary):
    """Order ban gaya: har deal ka discount likho (vendor ki payable se katne ke liye)."""
    from ..models import OrderDeal
    for line in summary.get('deals') or []:
        OrderDeal.objects.create(order=order, deal=line['deal'], vendor_id=order.vendor_id,
                                 title=line['title'][:80], amount=line['amount'])


def vendor_deals_total(vendor):
    """Vendor ki poori hui (delivered) orders par di gayi deals ka kul discount."""
    from django.db.models import Sum
    from ..models import OrderDeal
    t = OrderDeal.objects.filter(
        vendor=vendor, order__status__in=('delivered', 'invoiced', 'partially_delivered')
    ).aggregate(t=Sum('amount'))['t']
    return _q(t or 0)


# ------------------------------------------------------------ customer ko dikhane ke liye
def describe(deal):
    """Chhota text: '1+1 Free', '⚡ 20% off till 9:30 PM', 'Combo Rs 899'."""
    if deal.kind == 'bogo':
        return 'Buy 1 Get 1 Free'
    if deal.kind == 'combo':
        return f'Combo Rs {Decimal(deal.combo_price or 0):,.0f}'
    until = ''
    if deal.ends_at:
        until = ' till ' + timezone.localtime(deal.ends_at).strftime('%I:%M %p').lstrip('0')
    return f'\u26a1 {Decimal(deal.percent or 0).normalize():f}% off{until}'


def store_view(vendor_id):
    """Store page ke liye: ({product_id: chhota text}, [{'title', 'text', 'items'}])."""
    badges, strip = {}, []
    try:
        for d in active_deals(vendor_id):
            text = describe(d)
            names = []
            for it in d.items.all():
                names.append(it.product.name if it.qty == 1 else f'{it.qty} x {it.product.name}')
                badges.setdefault(it.product_id, text)
            strip.append({'title': d.title, 'text': text, 'items': ', '.join(names)})
    except Exception:
        logger.exception('Store deals view error')
    return badges, strip

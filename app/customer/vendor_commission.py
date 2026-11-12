"""
Vendor commission model (Amazon Seller Central jaisa).

- Vendor apna maal apni selling price par shop par bechta hai.
- Shop har bikri par commission % rakhta hai; baaqi paisa vendor ka hota hai.
- Stock batch ka "cost" = vendor ka hissa = (customer ki ada ki hui price) x (100 - commission) / 100.
  Is tarah FIFO, COGS aur profit ka purana logic waisa hi chalta hai, aur
  shop ka profit per sale = commission.
- Vendor ka discount vendor khud bardasht karta hai (commission discounted price par lagta hai).
"""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

from django.conf import settings
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

HUNDRED = Decimal('100')
CENT = Decimal('0.01')
MAX_COMMISSION = Decimal('50')


def default_commission():
    """settings.VENDOR_DEFAULT_COMMISSION_PERCENT (na ho to 10%)."""
    return Decimal(str(getattr(settings, 'VENDOR_DEFAULT_COMMISSION_PERCENT', 10)))


def base_commission_percent(profile):
    """Promo ke bina: vendor ka apna commission %, warna default."""
    pct = getattr(profile, 'commission_percent', None)
    return Decimal(pct) if pct is not None else default_commission()


def promo_active(profile, today=None):
    """Launch/promo commission abhi chalu hai? (date samet: 'till' wale din tak)"""
    pct = getattr(profile, 'commission_promo_percent', None)
    until = getattr(profile, 'commission_promo_until', None)
    if pct is None or until is None:
        return False
    return (today or timezone.localdate()) <= until


def margin_floor_commission():
    """Company ke 'minimum margin' rule (cost ka M%) ke hisab se sab se kam commission %.

    Vendor ka hissa == shop ka cost, is liye commission c% par margin = c / (100 - c) x 100 (cost ka %).
    M% margin ke liye c >= 100 x M / (100 + M). Isse kam promo hua to naye products batch banate waqt
    margin rule se reject ho jate. (Category ke apne margin rule is me shamil nahi.)"""
    from app.models import SystemSetting
    raw = SystemSetting.get_value('min_margin_percent', '0')
    try:
        m = Decimal(str(raw).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        return Decimal('0')
    if not m.is_finite() or m <= 0:
        return Decimal('0')
    return (HUNDRED * m / (HUNDRED + m)).quantize(CENT, ROUND_CEILING)


def commission_percent(profile):
    """Is vendor ka commission %. Launch promo chalu ho aur normal rate se kam ho to promo wala
    (company margin rule ke floor ke sath); warna vendor ka apna / default."""
    pct = base_commission_percent(profile)
    if promo_active(profile):
        promo = max(Decimal(profile.commission_promo_percent), margin_floor_commission())
        if promo < pct:
            return promo
    return pct


def effective_price(price, discount):
    """Customer jo price ada karta hai (discount ke baad)."""
    price = Decimal(price)
    discount = Decimal(discount or 0)
    return (price * (HUNDRED - discount) / HUNDRED).quantize(CENT, ROUND_HALF_UP)


def vendor_share(price, discount, pct):
    """Vendor ko har unit par milne wali raqam == batch ka 'cost'."""
    eff = effective_price(price, discount)
    share = (eff * (HUNDRED - Decimal(pct)) / HUNDRED).quantize(CENT, ROUND_HALF_UP)
    return max(share, CENT)


def reprice_open_batches(product, price, discount, pct):
    """Price/discount/commission badalne par product ke open batches (selling price + cost) update karo."""
    from app.models import StockBatch
    cost = vendor_share(price, discount, pct)
    price = Decimal(price)
    for batch in StockBatch.objects.filter(product=product, remaining_qty__gt=0):
        if batch.selling_price != price or batch.price != cost:
            batch.price = cost
            batch.selling_price = price
            batch.save()


def option_sale_item_fields(order_item):
    """SaleOrderItem se SaleItem banate waqt options ke fields.

    Extras ka vendor wala hissa = extra x (100 - commission) / 100, jo vendor_earnings mein payable
    mein jud jata hai. Marketplace ke bahar (vendor nahi) ke product par hissa 0 rehta hai."""
    extra = Decimal(getattr(order_item, 'options_extra', 0) or 0)
    fields = {'options_text': getattr(order_item, 'options_text', '') or ''}
    share = Decimal('0.00')
    vendor_id = getattr(order_item.product, 'vendor_id', None)
    if extra > 0 and vendor_id:
        from app.models import VendorProfile
        profile = VendorProfile.objects.filter(vendor_id=vendor_id).first()
        pct = commission_percent(profile) if profile else default_commission()
        share = (extra * (HUNDRED - pct) / HUNDRED).quantize(CENT, ROUND_HALF_UP)
    fields['options_extra_share'] = share
    return fields


def vendor_earnings(vendor):
    """Vendor ki ab tak ki bikri: sales, shop ka commission, aur vendor ka hissa (payable)."""
    from app.models import SaleItem, SaleItemBatchUsage
    agg = SaleItem.objects.filter(product__vendor=vendor).aggregate(sales=Sum('total_amt'), units=Sum('qty'))
    pay = SaleItemBatchUsage.objects.filter(sale_item__product__vendor=vendor).aggregate(
        payable=Sum(ExpressionWrapper(
            F('qty') * F('cost_price'), output_field=DecimalField(max_digits=18, decimal_places=2))))
    sales = Decimal(agg['sales'] or 0)
    extras = SaleItem.objects.filter(product__vendor=vendor).aggregate(
        t=Sum(ExpressionWrapper(
            F('qty') * F('options_extra_share'), output_field=DecimalField(max_digits=18, decimal_places=2))))['t']
    payable = (Decimal(pay['payable'] or 0) + Decimal(extras or 0)).quantize(CENT, ROUND_HALF_UP)
    from app.models import VendorPayout
    paid = Decimal(VendorPayout.objects.filter(vendor=vendor).aggregate(t=Sum('amount'))['t'] or 0)
    paid = paid.quantize(CENT, ROUND_HALF_UP)
    return {
        'units': agg['units'] or 0,
        'sales': sales,
        'commission': (sales - payable).quantize(CENT, ROUND_HALF_UP),
        'payable': payable,
        'paid': paid,
        'balance': (payable - paid).quantize(CENT, ROUND_HALF_UP),
    }


# ---------------------------------------------------------------- launch promo (naye vendor ka offer)
def reprice_vendor_batches(profile):
    """Vendor ke sab products ke open batches ka cost abhi ke commission_percent(profile) par karo.
    Commission batch ke cost me 'bake' hota hai, is liye rate badalne par ye zaroori hai.
    Return: un products ki list jin ka cost margin policy ki wajah se update nahi ho saka."""
    from django.core.exceptions import ValidationError
    from app.models import Product
    pct = commission_percent(profile)
    failed = []
    for product in Product.objects.filter(vendor=profile.vendor):
        base = product.original_price if product.original_price and product.original_price > 0 else product.price
        try:
            reprice_open_batches(product, base, product.discount_percentage, pct)
        except ValidationError as exc:
            failed.append(f'{product.name}: {"; ".join(exc.messages)}')
    return failed


def launch_promo_settings():
    """Settings > Shop: launch_promo_days (0 = band) aur launch_promo_percent."""
    from .offers import setting_decimal
    days = max(int(setting_decimal('launch_promo_days', '0')), 0)
    pct = min(max(setting_decimal('launch_promo_percent', '0'), Decimal('0')), MAX_COMMISSION)
    return {'days': days, 'percent': pct}


def grant_launch_promo(profile, today=None):
    """Naye vendor ko launch offer do (ek hi dafa). Approve hone wale din se `days` din (wo din samet).
    Return True agar abhi diya gaya."""
    cfg = launch_promo_settings()
    if cfg['days'] <= 0 or profile.launch_promo_granted_at:
        return False
    today = today or timezone.localdate()
    profile.commission_promo_percent = cfg['percent']
    profile.commission_promo_until = today + timedelta(days=cfg['days'] - 1)
    profile.launch_promo_granted_at = timezone.now()
    profile.save(update_fields=['commission_promo_percent', 'commission_promo_until', 'launch_promo_granted_at'])
    failed = reprice_vendor_batches(profile)
    if failed:
        logger.warning('Launch promo: cost update nahi hua (vendor=%s): %s', profile.pk, ' | '.join(failed[:5]))
    return True


def on_vendor_approved(profile, first_time):
    """Approve karne wali har jagah se bulao. Sirf pehli approval par offer; ghalti approval ko na roke."""
    if not first_time:
        return False
    from django.db import transaction
    try:
        with transaction.atomic():      # savepoint: ghalti ho to sirf promo wapas, caller ki transaction salamat
            return grant_launch_promo(profile)
    except Exception:
        logger.exception('Launch promo grant failed (vendor profile=%s)', getattr(profile, 'pk', None))
        return False


def expire_promos(profile=None, today=None):
    """Jin ki promo date guzar chuki unke open batches normal rate par reprice karo, phir promo saaf karo.
    Agar kisi product ka reprice na ho sake (margin policy) to promo ke fields rehne dete hain taake
    agli dafa dobara koshish ho. Return: kitne vendors normal par aaye."""
    from app.models import VendorProfile
    today = today or timezone.localdate()
    qs = VendorProfile.objects.filter(commission_promo_until__lt=today).select_related('vendor')
    if profile is not None:
        qs = qs.filter(pk=profile.pk)
    done = 0
    for p in qs:
        # date guzar chuki hai, is liye commission_percent(p) ab normal rate dega
        failed = reprice_vendor_batches(p)
        if failed:
            logger.warning('Promo expire: cost update nahi hua (vendor=%s): %s', p.pk, ' | '.join(failed[:5]))
            continue
        p.commission_promo_percent = None
        p.commission_promo_until = None
        p.save(update_fields=['commission_promo_percent', 'commission_promo_until'])
        done += 1
    return done

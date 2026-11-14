"""Vendor ki deals: Buy 1 Get 1 Free, Combo, Flash sale - vendor khud lagata aur band karta hai."""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from .vendor_access import get_vendor_profile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import Product, StoreDeal, StoreDealItem
from ..shop_flags import flag_required
from . import deals as deals_logic

logger = logging.getLogger(__name__)

DURATIONS = [(1, '1 hour'), (3, '3 hours'), (6, '6 hours'), (12, '12 hours'), (24, '1 day'), (72, '3 days'), (168, '7 days')]
COMBO_MAX_QTY = 5


def _dec(raw):
    try:
        return Decimal((raw or '').strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _sell_price(product):
    """Customer ko dikhne wali moti qeemat (discount ke baad) - combo ki qeemat ke andaze ke liye."""
    price = Decimal(product.price or 0)
    if product.discount_percentage and product.discount_percentage > 0:
        price = price * (Decimal('100') - Decimal(product.discount_percentage)) / Decimal('100')
    return price


@vendor_login_required
@flag_required('vendor_deals_enabled', redirect_to='vendor_dashboard')
def vendor_deals(request):
    profile = get_vendor_profile(request.user)
    if not profile.is_approved:
        messages.warning(request, '⏳ Your account has not been approved yet.')
        return redirect('vendor_dashboard')
    vendor = profile.vendor

    if request.method == 'POST':
        try:
            _create(request, profile, vendor)
        except Exception:
            logger.exception('Vendor deal error')
            messages.error(request, '❌ Something went wrong. Please try again')
        return redirect('vendor_deals')

    now = timezone.now()
    deals = list(profile.deals.prefetch_related('items__product')[:60])
    running = [d for d in deals if d.is_running(now)]
    others = [d for d in deals if not d.is_running(now)][:10]
    for d in running + others:
        d.text = deals_logic.describe(d)
        d.names = ', '.join(it.product.name if it.qty == 1 else f'{it.qty} x {it.product.name}' for it in d.items.all())
    products = list(Product.objects.filter(vendor=vendor, approval_status='approved', is_active=True).order_by('name'))
    return render(request, 'customer_portal/vendor/deals.html', {
        'profile': profile, 'products': products, 'running': running, 'others': others,
        'durations': DURATIONS, 'max_active': deals_logic.MAX_ACTIVE_PER_VENDOR,
        'max_flash': int(deals_logic.MAX_FLASH_PERCENT), 'combo_max_qty': COMBO_MAX_QTY,
    })


def _create(request, profile, vendor):
    post = request.POST
    kind = post.get('kind')
    if kind not in ('bogo', 'combo', 'flash'):
        messages.error(request, '❌ Choose a deal type.')
        return
    now = timezone.now()
    active = sum(1 for d in profile.deals.filter(is_active=True) if d.is_running(now))
    if active >= deals_logic.MAX_ACTIVE_PER_VENDOR:
        messages.error(request, f'❌ You can run up to {deals_logic.MAX_ACTIVE_PER_VENDOR} deals at once. End one first.')
        return

    ids = []
    for v in post.getlist('product_ids'):
        try:
            ids.append(int(v))
        except ValueError:
            continue
    products = {p.pk: p for p in Product.objects.filter(
        vendor=vendor, approval_status='approved', is_active=True, pk__in=ids)}
    chosen = [products[i] for i in dict.fromkeys(ids) if i in products]

    try:
        hours = int(post.get('duration') or 0)
    except ValueError:
        hours = 0
    if hours not in dict(DURATIONS) and hours != 0:
        hours = 0
    ends_at = now + timedelta(hours=hours) if hours else None

    percent = combo_price = None
    qtys = {}
    if kind == 'bogo':
        if len(chosen) != 1:
            messages.error(request, '❌ Choose exactly one product for Buy 1 Get 1.')
            return
        title = f'Buy 1 Get 1 Free: {chosen[0].name}'[:80]
    elif kind == 'flash':
        if not chosen:
            messages.error(request, '❌ Choose at least one product.')
            return
        percent = _dec(post.get('percent'))
        if percent is None or percent < 1 or percent > deals_logic.MAX_FLASH_PERCENT:
            messages.error(request, f'❌ Enter a discount between 1 and {int(deals_logic.MAX_FLASH_PERCENT)} percent.')
            return
        if not ends_at:
            messages.error(request, '❌ A flash sale needs an end time. Choose how long it runs.')
            return
        title = f'Flash sale {percent.normalize():f}% off'[:80]
    else:
        if len(chosen) < 2:
            messages.error(request, '❌ A combo needs at least two products.')
            return
        title = ' '.join((post.get('title') or '').split())[:60]
        if not title:
            messages.error(request, '❌ Give the combo a name.')
            return
        for p in chosen:
            try:
                q = int(post.get(f'qty_{p.pk}') or 1)
            except ValueError:
                q = 1
            qtys[p.pk] = min(max(q, 1), COMBO_MAX_QTY)
        combo_price = _dec(post.get('combo_price'))
        regular = sum((_sell_price(p) * qtys[p.pk] for p in chosen), Decimal('0'))
        if combo_price is None or combo_price <= 0 or combo_price >= regular:
            messages.error(request, f'❌ The combo price must be less than the normal total (about Rs. {regular:,.0f}).')
            return

    with transaction.atomic():
        deal = StoreDeal.objects.create(profile=profile, kind=kind, title=title, percent=percent,
                                        combo_price=combo_price, starts_at=now, ends_at=ends_at)
        StoreDealItem.objects.bulk_create(
            [StoreDealItem(deal=deal, product=p, qty=qtys.get(p.pk, 1)) for p in chosen])
    messages.success(request, '✅ Deal is live. Customers will see it on your store page and in the cart.')


@vendor_login_required
@require_POST
def vendor_deal_end(request, pk):
    profile = get_vendor_profile(request.user)
    deal = get_object_or_404(StoreDeal, pk=pk, profile=profile)
    deal.is_active = False
    deal.save(update_fields=['is_active'])
    messages.success(request, 'Deal ended.')
    return redirect('vendor_deals')

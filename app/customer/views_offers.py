"""Customer portal: Wallet, Pro membership aur "wallet se ada karein" ka switch.

Coupon lagana / hatana views_coupons.py mein hai; hisaab offers.py mein.
"""
import logging
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from django.db import transaction

from ..models import Customer, LoyaltyTransaction, ProMembership, WalletTransaction
from ..shop_flags import flag_required, shop_flag
from . import offers
from .views_customer_portal import get_cart_count_value
from .views_favorites import current_customer

logger = logging.getLogger(__name__)


def _back(request):
    nxt = request.POST.get('next', '')
    return redirect('checkout' if nxt == 'checkout' else 'cart_view')


@require_POST
@customer_login_required
@flag_required('shop_wallet_enabled')
def wallet_toggle(request):
    """Cart / checkout par 'Wallet se ada karein' on-off (session mein; order banne par hi paisa katta hai)."""
    use = request.POST.get('use') == '1'
    if use:
        request.session[offers.WALLET_SESSION_KEY] = True
    else:
        request.session.pop(offers.WALLET_SESSION_KEY, None)
    request.session.modified = True
    return _back(request)


@customer_login_required
@flag_required('shop_wallet_enabled')
def wallet_page(request):
    customer = current_customer(request)
    rows = list(WalletTransaction.objects.filter(customer=customer).select_related('order')[:60]) if customer else []
    return render(request, 'customer_portal/wallet.html', {
        'balance': offers.wallet_balance(customer),
        'rows': rows,
        'cashback_percent': offers.setting_decimal('cashback_percent', '0'),
        'cashback_max': offers.setting_decimal('cashback_max', '0'),
        'loyalty': _loyalty_context(customer),
        'funds': _funds_context(customer),
        'cart_count': get_cart_count_value(request),
    })


def _funds_context(customer):
    """Top-up / gift card hissa; ghalti par wallet page nahi rukta."""
    try:
        from . import wallet_funds
        return wallet_funds.wallet_context(customer)
    except Exception:
        logger.exception('Wallet funds context error')
        return None


def _loyalty_context(customer):
    cfg = offers.loyalty_settings()
    if not cfg['enabled'] or customer is None:
        return None
    bal = offers.points_balance(customer)
    return {
        **cfg,
        'balance': bal,
        'worth': (Decimal(bal) * cfg['value']).quantize(Decimal('0.01')),
        'can_redeem': bal >= cfg['min_redeem'] and cfg['value'] > 0,
        'rows': list(LoyaltyTransaction.objects.filter(customer=customer).select_related('order')[:15]),
    }


@require_POST
@customer_login_required
@flag_required('shop_wallet_enabled')
@flag_required('shop_loyalty_enabled')
def loyalty_redeem(request):
    """Loyalty points ko wallet credit mein badlo ('all' = sab points)."""
    customer = current_customer(request)
    if not customer:
        messages.error(request, '❌ Only a customer account can convert points.')
        return redirect('wallet_page')
    raw = (request.POST.get('points') or '').strip().lower()
    points = offers.points_balance(customer) if raw in ('all', '') else raw
    ok, msg = offers.redeem_points(customer, points)
    (messages.success if ok else messages.error)(request, ('🎁 ' if ok else '❌ ') + msg)
    return redirect('wallet_page')


@customer_login_required
@flag_required('shop_pro_enabled')
def pro_page(request):
    customer = current_customer(request)
    cfg = offers.pro_settings()
    active = offers.active_pro(customer) if customer else None
    pending = (ProMembership.objects.filter(customer=customer, status='pending').order_by('-requested_at').first()
               if customer else None)
    return render(request, 'customer_portal/pro.html', {
        'cfg': cfg,
        'active': active,
        'pending': pending,
        'can_pay_wallet': bool(customer and shop_flag('shop_wallet_enabled') and cfg['price'] > 0
                               and offers.wallet_balance(customer) >= cfg['price']),
        'wallet_balance': offers.wallet_balance(customer) if customer else 0,
        'cart_count': get_cart_count_value(request),
    })


@require_POST
@customer_login_required
@flag_required('shop_pro_enabled')
@flag_required('shop_wallet_enabled')
def pro_buy_wallet(request):
    """Pro ki fees wallet balance se (turant active; admin ke intezar ke baghair)."""
    customer = current_customer(request)
    cfg = offers.pro_settings()
    if not customer:
        messages.error(request, '❌ Only a customer account can get Pro.')
        return redirect('pro_page')
    price = cfg['price']
    if price <= 0:
        messages.info(request, 'Pro price is not set. Please send a request.')
        return redirect('pro_page')
    with transaction.atomic():
        Customer.objects.select_for_update().filter(pk=customer.pk).first()
        if offers.wallet_balance(customer) < price:
            messages.error(request, f'❌ Your wallet does not have Rs. {price:,.0f}.')
            return redirect('pro_page')
        member = (ProMembership.objects.select_for_update()
                  .filter(customer=customer, status='pending').order_by('-requested_at').first())
        if member is None:
            member = ProMembership(customer=customer, status='pending')
        member.amount = price
        member.note = 'Wallet se ada'
        member.activate(cfg['days'])
        WalletTransaction.objects.create(customer=customer, amount=-price, kind='pro',
                                         note=f"Pro {cfg['days']} din")
    messages.success(request, f"⭐ Pro is now active ({cfg['days']} days).")
    return redirect('pro_page')


@require_POST
@customer_login_required
@flag_required('shop_pro_enabled')
def pro_request(request):
    customer = current_customer(request)
    if not customer:
        messages.error(request, '❌ Only a customer account can get Pro.')
        return redirect('pro_page')
    if ProMembership.objects.filter(customer=customer, status='pending').exists():
        messages.info(request, 'You already have a Pro request. The shop will activate it after payment.')
        return redirect('pro_page')
    cfg = offers.pro_settings()
    ProMembership.objects.create(customer=customer, status='pending', amount=cfg['price'])
    try:
        from django.contrib.auth.models import User
        from ..models import Notification
        for admin in User.objects.filter(is_superuser=True, is_active=True):
            Notification.send(user=admin, title=f'⭐ Pro request - {customer.name}',
                              message=f'Phone: {customer.contact_number}\nRs. {cfg["price"]}. Payment lekar activate karein.',
                              notification_type='info', category='sales', link='/admin/app/promembership/')
    except Exception:
        logger.exception('Pro request notification failed')
    messages.success(request, '⭐ Request received. The shop will activate Pro once you pay.')
    return redirect('pro_page')

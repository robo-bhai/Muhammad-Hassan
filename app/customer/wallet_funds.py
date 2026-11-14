"""
Wallet top-up aur gift cards (bina online gateway ke).

Flow: customer request bhejta hai (raqam + payment ka reference) -> admin payment check kar ke Approve karta hai.
  - top-up : raqam wallet mein jama (WalletTransaction 'topup')
  - gift   : gift card ka code banta hai (khareedne wala dekh kar kisi ko bhej sakta hai)
Redeem: code likho -> raqam wallet mein (ek hi dafa; galat codes par thori der ke liye rok).
"""
import logging
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from ..shop_flags import shop_flag
from .offers import CENT, setting_decimal

logger = logging.getLogger(__name__)

CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'      # 0/O, 1/I jaise ulajhne wale hurf nahi
MAX_BAD_TRIES = 5
LOCK_SECONDS = 15 * 60
MAX_PENDING = 3


def enabled():
    return shop_flag('shop_wallet_enabled') and shop_flag('shop_gift_cards_enabled')


def limits():
    return {
        'min': setting_decimal('wallet_topup_min', '100'),
        'max': setting_decimal('wallet_topup_max', '50000'),
        'valid_days': int(setting_decimal('gift_card_valid_days', '365')),
    }


def parse_amount(raw):
    """'1,500' -> Decimal('1500.00'); galat ho to None."""
    try:
        val = Decimal(str(raw or '').replace(',', '').strip()).quantize(CENT)
    except (InvalidOperation, ValueError):
        return None
    return val if val > 0 else None


def normalize_code(raw):
    return ''.join(ch for ch in (raw or '').upper() if ch.isalnum())


def format_code(compact):
    return f'GC-{compact[:4]}-{compact[4:8]}'


def generate_code():
    """Unique code, jaise GC-7K4M-X2QD."""
    from ..models import GiftCard
    for _ in range(20):
        compact = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = format_code(compact)
        if not GiftCard.objects.filter(code=code).exists():
            return code
    raise RuntimeError('Gift card code banane mein masla')


def payment_info():
    """Customer ko dikhane ke liye shop ke payment account (Company Info se)."""
    from ..models import CompanyInfo
    c = CompanyInfo.objects.first()
    if not c:
        return {}
    info = {
        'JazzCash': c.jazzcash_number, 'EasyPaisa': c.easypaisa_number,
        'Bank': ' - '.join(x for x in (c.bank_account_title, c.bank_account_number) if x),
    }
    return {k: v for k, v in info.items() if v}


def _customer_user(customer):
    portal = getattr(customer, 'portal_profile', None)
    return getattr(portal, 'user', None)


def _notify(customer, title, message):
    from .store_orders import _notify as send
    send(_customer_user(customer), title, message, link='/shop/wallet/', kind='info')


def create_request(customer, kind, amount, method, reference, recipient_name='', message=''):
    """-> (request | None, error). Raqam Settings ki hadd ke andar; ek waqt mein MAX_PENDING se zyada pending nahi."""
    from ..models import WalletTopUp
    lim = limits()
    if not enabled():
        return None, 'Wallet top-up is not available right now.'
    if kind not in ('topup', 'gift'):
        return None, 'Invalid request.'
    if amount is None or amount < lim['min'] or (lim['max'] > 0 and amount > lim['max']):
        top = f" - Rs. {lim['max']:,.0f}" if lim['max'] > 0 else ''
        return None, f"Amount must be Rs. {lim['min']:,.0f}{top}."
    if method not in dict(WalletTopUp.METHOD_CHOICES):
        method = 'jazzcash'
    reference = (reference or '').strip()[:80]
    if not reference:
        return None, 'Please enter the transaction ID of your payment.'
    if WalletTopUp.objects.filter(customer=customer, status='pending').count() >= MAX_PENDING:
        return None, f'You already have {MAX_PENDING} requests waiting for approval.'
    if WalletTopUp.objects.filter(reference__iexact=reference, status__in=('pending', 'approved')).exists():
        return None, 'This transaction ID has already been used.'
    return WalletTopUp.objects.create(
        customer=customer, kind=kind, amount=amount, method=method, reference=reference,
        recipient_name=(recipient_name or '').strip()[:100], message=(message or '').strip()[:200]), ''


def approve(req, user=None, note=''):
    """Admin ne payment dekh li. -> (ok, message). Ek request sirf ek dafa approve hoti hai."""
    from ..models import GiftCard, WalletTopUp, WalletTransaction
    with transaction.atomic():
        req = WalletTopUp.objects.select_for_update().get(pk=req.pk)
        if req.status != 'pending':
            return False, 'Already reviewed.'
        if req.kind == 'topup':
            WalletTransaction.objects.create(customer=req.customer, amount=req.amount, kind='topup',
                                             note=f'{req.get_method_display()} {req.reference}'[:200], created_by=user)
            body = f'Rs. {req.amount:,.0f} has been added to your wallet.'
        else:
            days = limits()['valid_days']
            card = GiftCard.objects.create(
                code=generate_code(), amount=req.amount, buyer=req.customer, issued_by=user,
                recipient_name=req.recipient_name, message=req.message,
                expires_at=timezone.now() + timedelta(days=days) if days > 0 else None)
            req.gift_card = card
            body = f'Your Rs. {req.amount:,.0f} gift card is ready. Code: {card.code}'
        req.status, req.reviewed_by, req.reviewed_at, req.admin_note = 'approved', user, timezone.now(), (note or '')[:200]
        req.save()
    _notify(req.customer, 'Payment confirmed', body)
    return True, body


def reject(req, user=None, note=''):
    from ..models import WalletTopUp
    with transaction.atomic():
        req = WalletTopUp.objects.select_for_update().get(pk=req.pk)
        if req.status != 'pending':
            return False, 'Already reviewed.'
        req.status, req.reviewed_by, req.reviewed_at, req.admin_note = 'rejected', user, timezone.now(), (note or '')[:200]
        req.save()
    _notify(req.customer, 'Wallet request not approved',
            f'We could not verify your payment of Rs. {req.amount:,.0f}.' + (f' {req.admin_note}' if req.admin_note else ''))
    return True, 'Rejected.'


def _lock_key(customer):
    return f'giftcard_bad:{customer.pk}'


def redeem(customer, raw_code):
    """Gift card ka code wallet mein. -> (ok, message)."""
    from ..models import GiftCard, WalletTransaction
    if not enabled():
        return False, 'Gift cards are not available right now.'
    if (cache.get(_lock_key(customer)) or 0) >= MAX_BAD_TRIES:
        return False, 'Too many wrong codes. Please try again in 15 minutes.'
    compact = normalize_code(raw_code)
    if compact.startswith('GC'):
        compact = compact[2:]
    if len(compact) != 8:
        return _bad(customer)
    with transaction.atomic():
        card = GiftCard.objects.select_for_update().filter(code=format_code(compact)).first()
        if card is None:
            return _bad(customer)
        if card.status != 'active':
            return False, 'This gift card has already been used or is cancelled.'
        if card.expires_at and card.expires_at < timezone.now():
            return False, 'This gift card has expired.'
        card.status, card.redeemed_by, card.redeemed_at = 'redeemed', customer, timezone.now()
        card.save(update_fields=['status', 'redeemed_by', 'redeemed_at'])
        WalletTransaction.objects.create(customer=customer, amount=card.amount, kind='giftcard', note=card.code)
    cache.delete(_lock_key(customer))
    return True, f'Rs. {card.amount:,.0f} added to your wallet.'


def _bad(customer):
    key = _lock_key(customer)
    cache.set(key, (cache.get(key) or 0) + 1, LOCK_SECONDS)
    return False, 'Invalid gift card code.'


def wallet_context(customer):
    """Wallet page ke liye: payment accounts, hadd, customer ki requests aur khareede hue gift cards."""
    from ..models import GiftCard, WalletTopUp
    if customer is None or not enabled():
        return None
    return {
        'payment': payment_info(), 'limits': limits(),
        'requests': list(WalletTopUp.objects.filter(customer=customer)[:10]),
        'cards': list(GiftCard.objects.filter(buyer=customer)[:10]),
    }

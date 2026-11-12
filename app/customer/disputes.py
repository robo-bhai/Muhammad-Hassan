"""Dispute (masla report) ka business logic: kab khul sakta hai, aur admin ke faisle par refund.

Views is file ke functions use karte hain; yahan koi request/HTTP nahi, taake test aasan ho.
"""
import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import store_orders
from .offers import setting_decimal

logger = logging.getLogger(__name__)

CENT = Decimal('0.01')
ELIGIBLE_STATUSES = ('delivered', 'invoiced')
MAX_PHOTO_BYTES = 5 * 1024 * 1024


class DisputeError(Exception):
    """Aisi galti jo customer/admin ko seedha dikhai ja sakti hai."""


def window_hours():
    return max(int(setting_decimal('dispute_window_hours', '48')), 1)


def delivered_at(order):
    from ..models import DeliveryInfo
    di = DeliveryInfo.objects.filter(sale_order=order, delivered_at__isnull=False).order_by('-delivered_at').first()
    return di.delivered_at if di else order.updated_at


def can_open_dispute(order):
    """(True, '') ya (False, wajah). Order delivered ho, window ke andar ho, aur pehle dispute na ho."""
    if order.status not in ELIGIBLE_STATUSES:
        return False, 'Dispute sirf deliver hue order par ho sakta hai.'
    if hasattr(order, 'dispute'):
        return False, 'Is order par dispute pehle se mojood hai.'
    if timezone.now() > delivered_at(order) + timedelta(hours=window_hours()):
        return False, f'Dispute deliver hone ke {window_hours()} ghante ke andar hi ho sakta hai.'
    return True, ''


def max_refund(order):
    return Decimal(store_orders.order_payable_total(order) or 0).quantize(CENT, ROUND_HALF_UP)


def check_photo(photo):
    if photo is None:
        return
    if photo.size > MAX_PHOTO_BYTES:
        raise DisputeError('Photo 5 MB se choti honi chahiye.')
    if not (getattr(photo, 'content_type', '') or '').startswith('image/'):
        raise DisputeError('Sirf image (photo) upload karein.')


def short_name(customer):
    """Privacy: vendor/rider ko poora naam nahi, 'Hadi Ahmed' -> 'Hadi A.'"""
    parts = (getattr(customer, 'name', '') or 'Customer').split()
    return parts[0] + (f' {parts[-1][0]}.' if len(parts) > 1 else '')


def _user_for_vendor(vendor_id):
    from ..models import VendorProfile
    vp = VendorProfile.objects.filter(vendor_id=vendor_id).select_related('user').first() if vendor_id else None
    return vp.user if vp else None


def open_dispute(order, reason, description='', photo=None):
    from ..models import DeliveryInfo, OrderDispute
    ok, why = can_open_dispute(order)
    if not ok:
        raise DisputeError(why)
    if reason not in dict(OrderDispute.REASON_CHOICES):
        raise DisputeError('Choose the reason for the issue.')
    description = (description or '').strip()[:2000]
    if reason == 'other' and not description:
        raise DisputeError('If you choose "Other", please describe the issue.')
    check_photo(photo)

    di = DeliveryInfo.objects.filter(sale_order=order, rider__isnull=False).select_related('rider').first()
    try:
        with transaction.atomic():
            dispute = OrderDispute.objects.create(
                sale_order=order, customer_id=order.customer_id, vendor_id=order.vendor_id,
                rider=di.rider if di else None, reason=reason, description=description, photo=photo)
    except IntegrityError:
        raise DisputeError('Is order par dispute pehle se mojood hai.')

    label = dispute.get_reason_display()
    store_orders._notify(_user_for_vendor(order.vendor_id), f'⚠️ Dispute: order #{order.order_no}',
                         f'Customer ne masla report kiya: {label}.', '/shop/vendor/', 'warning')
    if dispute.rider_id:
        store_orders._notify(dispute.rider.user, f'⚠️ Dispute: order #{order.order_no}',
                             f'Customer ne masla report kiya: {label}.', '/shop/rider/', 'warning')
    return dispute


def mark_under_review(dispute, user):
    if dispute.status != 'open':
        raise DisputeError('Only an open dispute can be moved to review.')
    dispute.status = 'under_review'
    dispute.save(update_fields=['status', 'updated_at'])
    store_orders._notify(store_orders._customer_user(dispute.sale_order), 'Dispute is under review',
                         f'Order #{dispute.sale_order.order_no} ka masla dekha ja raha hai.',
                         f'/shop/order/{dispute.sale_order_id}/', 'info')
    return dispute


def resolve_dispute(dispute, action, user, amount=None, note=''):
    """action: 'refund_full' | 'refund_partial' | 'reject'. Wallet refund ek hi dafa banta hai."""
    from ..models import OrderDispute, WalletTransaction
    note = (note or '').strip()[:300]
    if action not in ('refund_full', 'refund_partial', 'reject'):
        raise DisputeError('Galat faisla.')

    with transaction.atomic():
        dispute = OrderDispute.objects.select_for_update().select_related('sale_order').get(pk=dispute.pk)
        if not dispute.is_open:
            raise DisputeError('Is dispute ka faisla ho chuka hai.')
        order = dispute.sale_order
        cap = max_refund(order)

        refund = Decimal('0.00')
        if action == 'refund_full':
            refund = cap
        elif action == 'refund_partial':
            try:
                refund = Decimal(str(amount)).quantize(CENT, ROUND_HALF_UP)
            except Exception:
                raise DisputeError('Enter a valid refund amount.')
            if refund <= 0 or refund > cap:
                raise DisputeError(f'Refund 0 se zyada aur {cap} se kam ya barabar honi chahiye.')
        elif not note:
            raise DisputeError('A reason is required to reject.')

        if refund > 0:
            if cap <= 0:
                raise DisputeError('This order amount is zero, so it cannot be refunded.')
            _, created = WalletTransaction.objects.get_or_create(
                order=order, kind='dispute',
                defaults={'customer_id': dispute.customer_id, 'amount': refund,
                          'note': f'Dispute refund: order #{order.order_no}', 'created_by': user})
            if not created:
                raise DisputeError('Is order ka dispute refund pehle ho chuka hai.')

        dispute.status = 'rejected' if action == 'reject' else 'resolved'
        dispute.resolution = 'no_refund' if action == 'reject' else action
        dispute.refund_amount = refund
        dispute.admin_note = note
        dispute.resolved_by = user
        dispute.resolved_at = timezone.now()
        dispute.save()

    if refund > 0:
        msg = f'Aap ke wallet mein {refund} wapas aa gaye hain.'
        title = 'Dispute resolve ho gaya'
    else:
        msg = note or 'The dispute was rejected.'
        title = 'Dispute par faisla'
    store_orders._notify(store_orders._customer_user(order), f'{title} (order #{order.order_no})', msg,
                         f'/shop/order/{order.id}/', 'success' if refund > 0 else 'info')
    return dispute


# ---------------------------------------------------------------- vendor / rider ka jawab
RESPONSE_MAX_CHARS = 1000


def disputes_for(party, obj):
    """party: 'vendor' ya 'rider'; obj: Vendor ya RiderProfile. Sirf usi ke disputes."""
    from ..models import OrderDispute
    qs = OrderDispute.objects.select_related('sale_order', 'customer')
    return qs.filter(vendor=obj) if party == 'vendor' else qs.filter(rider=obj)


def needs_response_count(party, obj):
    """Kitne open disputes par is party ne abhi jawab nahi diya (badge ke liye)."""
    qs = disputes_for(party, obj).filter(status__in=('open', 'under_review'))
    return qs.filter(vendor_responded_at__isnull=True).count() if party == 'vendor' \
        else qs.filter(rider_responded_at__isnull=True).count()


def submit_response(dispute, party, text, photo=None):
    """Vendor/rider apna jawab ek dafa darj karta hai. Admin ko khabar jati hai."""
    from ..models import OrderDispute
    if party not in ('vendor', 'rider'):
        raise DisputeError('Galat party.')
    text = (text or '').strip()
    if not text:
        raise DisputeError('A reply is required.')
    if len(text) > RESPONSE_MAX_CHARS:
        raise DisputeError(f'Jawab {RESPONSE_MAX_CHARS} harf se chota likhein.')
    check_photo(photo)

    with transaction.atomic():
        dispute = OrderDispute.objects.select_for_update().select_related('sale_order').get(pk=dispute.pk)
        if not dispute.is_open:
            raise DisputeError('This dispute is already decided, so a reply can no longer be given.')
        if getattr(dispute, f'{party}_responded_at'):
            raise DisputeError('You have already replied.')
        setattr(dispute, f'{party}_response', text)
        if photo is not None:
            setattr(dispute, f'{party}_photo', photo)
        setattr(dispute, f'{party}_responded_at', timezone.now())
        dispute.save()

    _notify_admins(dispute, party)
    return dispute


def _notify_admins(dispute, party):
    from django.contrib.auth.models import User
    who = 'Store' if party == 'vendor' else 'Rider'
    for user in User.objects.filter(is_superuser=True, is_active=True):
        store_orders._notify(user, f'{who} ne dispute ka jawab diya',
                             f'Order #{dispute.sale_order.order_no}: {who} ka jawab aa gaya hai.',
                             f'/disputes/{dispute.pk}/', 'info')

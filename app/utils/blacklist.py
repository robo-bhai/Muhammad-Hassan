"""Blacklist helpers: blocked phone / email / device pakadna aur block karna.

Blacklist sirf NAYE accounts rokti hai (register par). Pehle se bane account ko Suspend rokta hai.
Device = IP + browser ka HMAC hash (referrals.device_hash). Yeh kamzor pehchan hai: shared WiFi ya
mobile network par dusre log bhi isi hash par aa sakte hain, isliye device block hamesha opt-in hai.
"""
import logging

from django.db.models import Q

from ..models import BlockedIdentity
from .phone_utils import is_comparable, phone_key

logger = logging.getLogger(__name__)

BLOCKED_MSG = '⛔ Is phone/email/device se registration ki ijazat nahi hai. Madad ke liye store se rabta karein.'


def _norm(kind, value):
    value = (value or '').strip()
    if kind == BlockedIdentity.KIND_PHONE:
        return phone_key(value) if is_comparable(value) else ''
    if kind == BlockedIdentity.KIND_EMAIL:
        v = value.lower()
        return v if '@' in v else ''
    return value[:64]            # device hash


def current_device(request):
    """Is request ka device hash ('' agar nikal na sake)."""
    try:
        from ..customer.referrals import device_hash
        return device_hash(request) or ''
    except Exception:
        logger.exception('blacklist: device hash failed')
        return ''


def blocked_identity(phone=None, email=None, device=None):
    """Pehli active blocked entry jo in mein se kisi se match kare, warna None."""
    cond = Q()
    p = _norm('phone', phone)
    e = _norm('email', email)
    d = _norm('device', device)
    if p:
        cond |= Q(kind='phone', value=p)
    if e:
        cond |= Q(kind='email', value=e)
    if d:
        cond |= Q(kind='device', value=d)
    if not cond:
        return None
    return BlockedIdentity.objects.filter(is_active=True).filter(cond).first()


def block_identity(kind, value, label='', reason='', source='manual', source_ref='', user=None):
    """Ek cheez block karo (pehle se ho to dobara active). Bekaar value par None."""
    v = _norm(kind, value)
    if not v:
        return None
    obj, _ = BlockedIdentity.objects.update_or_create(
        kind=kind, value=v,
        defaults=dict(is_active=True, label=(label or (value if kind != 'device' else 'Device'))[:120],
                      reason=(reason or '')[:255], source=source, source_ref=source_ref[:40],
                      created_by=user if getattr(user, 'pk', None) else None))
    return obj


def block_account(phones=(), emails=(), device='', reason='', source='manual', source_ref='', user=None):
    """Ek account ki saari pehchaan block karo. Wapas: kitni entries bani/active hui."""
    n = 0
    for ph in phones:
        n += bool(block_identity('phone', ph, reason=reason, source=source, source_ref=source_ref, user=user))
    for em in emails:
        n += bool(block_identity('email', em, reason=reason, source=source, source_ref=source_ref, user=user))
    if device:
        n += bool(block_identity('device', device, label='Device (IP + browser)', reason=reason,
                                 source=source, source_ref=source_ref, user=user))
    if n:
        logger.warning('Blacklist: %s entries (%s) by %s. Reason: %s', n, source_ref or source, user, reason or '-')
    return n


def unblock_ref(source_ref):
    """Kisi account (customer:12 / vendor:5) ki saari blacklist entries hata do (unsuspend par)."""
    if not source_ref:
        return 0
    deleted, _ = BlockedIdentity.objects.filter(source_ref=source_ref).delete()
    return deleted

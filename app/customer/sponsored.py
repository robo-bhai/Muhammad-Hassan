"""
Sponsored / Featured store (vendor paise de kar upar aaye - shop ki extra income).

- Vendor "Promote my store" page se request bhejta hai (pending).
- Payment milne par admin Activate karta hai (Admin > Store Sponsorships); mudat Settings se.
- Active sponsorship wale stores store list (Recommended sort) aur homepage par pehle aate hain, 'Sponsored' tag ke saath.
- Band (closed) store kabhi khule store se upar nahi aata.
"""
import logging
from decimal import Decimal

from django.utils import timezone

from ..shop_flags import shop_flag

logger = logging.getLogger(__name__)


def sponsored_settings():
    from .offers import setting_decimal
    return {
        'enabled': shop_flag('shop_sponsored_enabled'),
        'price': max(setting_decimal('sponsored_price', '0'), Decimal('0')),
        'days': max(int(setting_decimal('sponsored_days', '7')), 1),
        'max_slots': max(int(setting_decimal('sponsored_max_slots', '5')), 0),
    }


def sponsored_profile_ids(today=None):
    """Abhi sponsored VendorProfile ids (flag off ho to khali). Slots se zyada hon to pehle shuru hone wale."""
    try:
        cfg = sponsored_settings()
        if not cfg['enabled']:
            return set()
        from ..models import StoreSponsorship
        today = today or timezone.localdate()
        rows = (StoreSponsorship.objects.filter(status='active', starts_on__lte=today, ends_on__gte=today)
                .order_by('starts_on', 'pk').values_list('profile_id', flat=True))
        ids = []
        for pid in rows:
            if pid not in ids:
                ids.append(pid)
        if cfg['max_slots']:
            ids = ids[:cfg['max_slots']]
        return set(ids)
    except Exception:
        logger.exception('sponsored_profile_ids failed')
        return set()


def vendor_status(profile, today=None):
    """Vendor page ke liye: {'running': sponsorship ya None, 'pending': sponsorship ya None}."""
    from ..models import StoreSponsorship
    today = today or timezone.localdate()
    qs = StoreSponsorship.objects.filter(profile=profile)
    running = (qs.filter(status='active', ends_on__gte=today).order_by('-ends_on').first())
    pending = qs.filter(status='pending').order_by('-requested_at').first()
    return {'running': running, 'pending': pending}

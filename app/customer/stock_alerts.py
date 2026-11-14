"""
Vendor ke liye stock ki khabar.

- Stock 0 ho to maal customer ko khud-ba-khud "Out of stock" dikhta hai (order nahi hota) aur restock par khud wapas khul jata hai;
  vendor ko "Sold out" ki notification milti hai.
- Stock Settings ke "low level" tak gir jaye to vendor ko "Low stock" notification (ek maal par 12 ghante mein ek dafa).
- Sirf vendor ke apne approved + active maal par; shop ke apne maal ka alert pehle jaisa (app/signals.py).
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from ..shop_flags import shop_flag

logger = logging.getLogger(__name__)

REPEAT_HOURS = 12


def low_stock_settings():
    from .offers import setting_decimal
    return {
        'enabled': shop_flag('vendor_low_stock_alert_enabled'),
        'level': max(int(setting_decimal('vendor_low_stock_level', '5')), 1),
    }


def stock_state(total, level):
    """'out' (0 ya kam) / 'low' (level tak) / 'ok'."""
    total = float(total or 0)
    if total <= 0:
        return 'out'
    return 'low' if total <= level else 'ok'


def effective_level(profile, cfg):
    """Vendor ki apni low-stock hadd (khali ho to shop ki default)."""
    own = getattr(profile, 'low_stock_level', None)
    return max(int(own), 1) if own else cfg['level']


def hide_sold_out(qs):
    """Jin vendors ne 'Hide sold-out products' chalu kiya, unka stock-0 maal queryset se hata do (restock par khud wapas)."""
    from ..models import Inventory, Product
    in_stock = Inventory.objects.values('product_id').annotate(t=Sum('stock')).filter(t__gt=0).values('product_id')
    hidden = Product.objects.filter(vendor__portal_profile__hide_sold_out=True).exclude(pk__in=in_stock).values('pk')
    return qs.exclude(pk__in=hidden)


def _already_sent(user, title):
    from ..models import Notification
    since = timezone.now() - timedelta(hours=REPEAT_HOURS)
    return Notification.objects.filter(user=user, title=title, created_at__gte=since).exists()


def check_product(product_id):
    """Is maal ka kul stock dekh kar zaroorat ho to vendor ko khabar do. Return: 'out' / 'low' / None."""
    from ..models import Inventory, Product, VendorProfile
    from .store_orders import _notify

    cfg = low_stock_settings()
    if not cfg['enabled']:
        return None
    product = Product.objects.filter(pk=product_id, vendor__isnull=False,
                                     approval_status='approved', is_active=True).first()
    if not product:
        return None
    total = Inventory.objects.filter(product_id=product.pk).aggregate(t=Sum('stock'))['t'] or 0
    profile = VendorProfile.objects.filter(vendor_id=product.vendor_id).select_related('user', 'parent', 'parent__user').first()
    if not profile or not profile.user_id:
        return None
    level = effective_level(profile, cfg)
    state = stock_state(total, level)
    if state == 'ok':
        return None

    name = (product.name or '')[:100]
    if state == 'out':
        title = f'\u274c Sold out: {name}'
        body = ('Stock is finished. Customers no longer see it until you add more.' if profile.hide_sold_out
                else 'Stock is finished. Customers see it as out of stock until you add more.')
        kind = 'danger'
    else:
        title = f'\U0001F4E6 Low stock: {name}'
        body = f'Only {total:g} left (alert at {level} or less). Add stock to keep selling.'
        kind = 'warning'
    target = profile.parent.user if profile.parent_id else profile.user    # branch ka login nahi: owner ko
    if profile.parent_id:
        title = f'{title} [{profile.branch_name}]'
    if _already_sent(target, title):
        return None
    _notify(target, title, body, '/shop/vendor/', kind)
    return state


@receiver(post_save, sender='app.Inventory', dispatch_uid='vendor_low_stock_alert')
def vendor_stock_signal(sender, instance, created, **kwargs):
    try:
        if created or not instance.product.vendor_id:
            return
        pid = instance.product_id
        # transfer / multi-warehouse update poora hone ke baad dekho (beech ka giraa hua stock jhoota alert na de)
        transaction.on_commit(lambda: _safe_check(pid))
    except Exception:       # alert ki kisi galti se stock ka kaam kabhi na rukey
        logger.exception('Vendor stock signal error')


def _safe_check(pid):
    try:
        check_product(pid)
    except Exception:
        logger.exception('Vendor stock check failed (product=%s)', pid)

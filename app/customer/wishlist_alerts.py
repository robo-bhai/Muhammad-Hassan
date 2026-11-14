"""
Wishlist alerts (customer):

- Back in stock : wishlist ka maal stock 0 tha aur ab wapas aa gaya -> customer ko notification + push.
- Price drop    : wishlist ka maal sasta ho gaya (customer ne jo qeemat aakhri dafa dekhi thi usse kam) -> notification + push.

Kaise chalta hai:
- Inventory / Product / StockBatch save hone par signal (transaction commit ke baad) check_product() chalata hai.
- Jo badlav signal se na pakde jayen (bulk update waghera) unke liye:  python manage.py send_wishlist_alerts
  (cron / scheduler se har 10-15 minute mein chalayen).
- Customer har item par apne alerts band/chalu kar sakta hai (Favourites > Items).
- Admin switch: Settings > Shop > "Wishlist alerts" (shop_wishlist_alerts_enabled).
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from ..shop_flags import shop_flag

logger = logging.getLogger(__name__)

MIN_DROP_PERCENT = Decimal('1')       # 1% se kam farq par alert nahi (rounding ka shor)
MIN_DROP_RS = Decimal('1')            # ya kam az kam Rs 1
PRICE_ALERT_GAP_HOURS = 6             # ek item par price alert 6 ghante mein ek dafa


def alerts_enabled():
    return shop_flag('shop_favorites_enabled') and shop_flag('shop_wishlist_alerts_enabled')


def _live_product(product_id):
    from ..models import Product
    return Product.objects.filter(pk=product_id, vendor__isnull=False, approval_status='approved',
                                  is_active=True).first()


def _total_stock(product_id):
    from ..models import Inventory
    return float(Inventory.objects.filter(product_id=product_id).aggregate(t=Sum('stock'))['t'] or 0)


def _customer_user(customer):
    portal = getattr(customer, 'portal_profile', None)
    return getattr(portal, 'user', None)


def _money(value):
    return f"Rs. {Decimal(value):,.0f}"


def _send(user, title, body, product):
    from .store_orders import _notify
    _notify(user, title, body, link=f'/shop/product/{product.pk}/', kind='info')


def _store_label(product):
    from .store_orders import store_name
    try:
        return store_name(product.vendor_id) or ''
    except Exception:
        return ''


def is_real_drop(old, new):
    """Kya new, old se itna sasta hai ke alert banta hai?"""
    if old is None or new is None or new >= old or old <= 0:
        return False
    diff = old - new
    return diff >= MIN_DROP_RS or (diff / old * 100) >= MIN_DROP_PERCENT


def current_price(product):
    from .views_customer_portal import get_product_final_price
    return Decimal(get_product_final_price(product) or 0).quantize(Decimal('0.01'))


def check_product(product_id):
    """Is maal ki wishlist wale customers ko zaroorat ho to alert do. Return: (stock_alerts, price_alerts)."""
    from ..models import WishlistItem

    if not alerts_enabled():
        return 0, 0
    product = _live_product(product_id)
    if not product:
        return 0, 0

    items = list(WishlistItem.objects.filter(product_id=product.pk).select_related('customer'))
    if not items:
        return 0, 0

    stock = _total_stock(product.pk)
    price = current_price(product)
    in_stock = stock > 0
    now = timezone.now()
    store = _store_label(product)
    name = (product.name or '')[:100]
    stock_sent = price_sent = 0

    for item in items:
        changed = set()

        # ---- Back in stock ----
        if not in_stock:
            if not item.was_out_of_stock:
                item.was_out_of_stock = True
                changed.add('was_out_of_stock')
        elif item.was_out_of_stock:
            item.was_out_of_stock = False
            changed.add('was_out_of_stock')
            user = _customer_user(item.customer)
            if item.notify_stock and user:
                _send(user, f'\U0001F514 Back in stock: {name}',
                      f'{name}{" from " + store if store else ""} is available again. Order now before it sells out.',
                      product)
                item.last_alert_at = now
                changed.add('last_alert_at')
                stock_sent += 1

        # ---- Price drop (stock mein ho to hi; out of stock par sasti qeemat ka faida nahi) ----
        if item.last_price is None:
            item.last_price = price
            changed.add('last_price')
        elif price != item.last_price:
            if in_stock and is_real_drop(item.last_price, price):
                user = _customer_user(item.customer)
                recently = item.last_alert_at and (now - item.last_alert_at) < timedelta(hours=PRICE_ALERT_GAP_HOURS)
                if item.notify_price and user and not recently:
                    off = int(round((item.last_price - price) / item.last_price * 100))
                    _send(user, f'\U0001F4C9 Price drop: {name}',
                          f'Now {_money(price)} (was {_money(item.last_price)}, {off}% off)'
                          f'{" at " + store if store else ""}. Tap to order.',
                          product)
                    item.last_alert_at = now
                    changed.add('last_alert_at')
                    price_sent += 1
            item.last_price = price          # badhi ho ya ghati: naya "dekha hua" daam
            changed.add('last_price')

        if changed:
            item.save(update_fields=list(changed))
    return stock_sent, price_sent


def snapshot_for_item(item):
    """Wishlist mein naya maal daalte waqt: abhi ki qeemat aur stock ki halat yaad rakho."""
    try:
        product = item.product
        item.last_price = current_price(product)
        item.was_out_of_stock = _total_stock(product.pk) <= 0
        item.save(update_fields=['last_price', 'was_out_of_stock'])
    except Exception:
        logger.exception('Wishlist snapshot failed (item=%s)', getattr(item, 'pk', None))


# ---------------------------------------------------------------- signals
def _safe_check(pid):
    try:
        check_product(pid)
    except Exception:
        logger.exception('Wishlist alert check failed (product=%s)', pid)


def _schedule(pid):
    # transfer / multi-warehouse update poora hone ke baad dekho
    transaction.on_commit(lambda: _safe_check(pid))


@receiver(post_save, sender='app.Inventory', dispatch_uid='wishlist_alert_inventory')
def wishlist_inventory_signal(sender, instance, created, **kwargs):
    try:
        _schedule(instance.product_id)
    except Exception:
        logger.exception('Wishlist inventory signal error')


@receiver(post_save, sender='app.Product', dispatch_uid='wishlist_alert_product')
def wishlist_product_signal(sender, instance, created, **kwargs):
    try:
        if not created and instance.vendor_id:
            _schedule(instance.pk)
    except Exception:
        logger.exception('Wishlist product signal error')


@receiver(post_save, sender='app.StockBatch', dispatch_uid='wishlist_alert_batch')
def wishlist_batch_signal(sender, instance, created, **kwargs):
    try:
        _schedule(instance.product_id)
    except Exception:
        logger.exception('Wishlist batch signal error')


def sweep():
    """Sab wishlist maal ek dafa dekh lo (signal se chhoote hue badlav ke liye). Return: (stock_alerts, price_alerts)."""
    from ..models import WishlistItem
    totals = [0, 0]
    for pid in WishlistItem.objects.values_list('product_id', flat=True).distinct():
        s, p = check_product(pid)
        totals[0] += s
        totals[1] += p
    return tuple(totals)

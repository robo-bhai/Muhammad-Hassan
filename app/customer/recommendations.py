"""
Personal recommendations (shop home par):
  1. "Order again"        - customer ke pichle orders (har store ka sab se naya), ek click mein reorder.
  2. "Your favourites"    - jo maal customer ne sab se zyada baar mangwaya (delivered orders se).
  3. "Trending near you"  - pichle kuch din mein sab se zyada bikne wala maal, un stores ka jo customer ke area mein deliver karte hain.
Band / out-of-stock maal aur band store nahi dikhte. Koi galti ho to home page nahi tootta (khali rows).
"""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Sum
from django.utils import timezone

from ..shop_flags import shop_flag

logger = logging.getLogger(__name__)

DONE_STATUSES = ('delivered', 'invoiced', 'partially_delivered')
ROW_SIZE = 8
REORDER_SIZE = 3
TRENDING_CACHE_SECONDS = 600


def reco_settings():
    from .offers import setting_decimal
    return {
        'enabled': shop_flag('shop_recommendations_enabled'),
        'days': min(max(int(setting_decimal('reco_trending_days', '14')), 1), 90),
        'min_orders': max(int(setting_decimal('reco_trending_min_orders', '2')), 1),
    }


def _store_map(vendor_ids):
    from ..models import VendorProfile
    return {p.vendor_id: p for p in VendorProfile.objects.filter(is_approved=True, vendor_id__in=set(vendor_ids))}


def _product_cards(product_ids):
    """product_ids ki tarteeb mein live + stock wale products ke cards."""
    from ..models import Product
    from .views_customer_portal import get_product_final_price
    ids = list(dict.fromkeys(product_ids))
    if not ids:
        return []
    products = {p.pk: p for p in Product.objects.filter(
        pk__in=ids, is_active=True, approval_status='approved', vendor__isnull=False,
    ).annotate(total_stock=Sum('inventory__stock')).filter(total_stock__gt=0)}
    stores = _store_map(p.vendor_id for p in products.values())
    cards = []
    for pid in ids:
        p = products.get(pid)
        store = stores.get(p.vendor_id) if p else None
        if not p or not store or store.status_label == 'closed':
            continue
        try:
            price = get_product_final_price(p)
        except Exception:
            price = p.price
        cards.append({'id': p.pk, 'name': p.name, 'image': p.image, 'price': price,
                      'store_name': store.business_name, 'store_id': store.pk})
        if len(cards) >= ROW_SIZE:
            break
    return cards


def reorder_cards(customer, limit=REORDER_SIZE):
    """Har store ka sab se naya poora hua order."""
    from ..models import SaleOrder
    from .store_orders import ZERO
    orders = (SaleOrder.objects.filter(customer=customer, status__in=DONE_STATUSES, vendor__isnull=False)
              .order_by('-order_date').prefetch_related('items__product')[:40])
    seen, picked = set(), []
    for o in orders:
        if o.vendor_id in seen:
            continue
        seen.add(o.vendor_id)
        picked.append(o)
        if len(picked) >= limit:
            break
    stores = _store_map(o.vendor_id for o in picked)
    cards = []
    for o in picked:
        store = stores.get(o.vendor_id)
        if not store or store.status_label == 'closed':
            continue
        items = list(o.items.all())
        names = [i.product.name for i in items[:2]]
        more = len(items) - len(names)
        total = sum(((i.price or ZERO) * (i.qty or 0) for i in items), ZERO)
        cards.append({'order_id': o.pk, 'store_name': store.business_name, 'store_id': store.pk,
                      'summary': ', '.join(names) + (f' +{more}' if more > 0 else ''),
                      'total': total, 'date': o.order_date})
    return cards


def favourite_ids(customer, limit=30):
    """Customer ne sab se zyada kis maal ko mangwaya (alag alag orders ginay jate hain)."""
    from ..models import SaleOrderItem
    rows = (SaleOrderItem.objects.filter(order__customer=customer, order__status__in=DONE_STATUSES,
                                         product__vendor__isnull=False)
            .values('product_id').annotate(n=Count('order', distinct=True), q=Sum('qty'))
            .order_by('-n', '-q')[:limit])
    return [r['product_id'] for r in rows]


def trending_ids(area, days, min_orders, limit=30):
    """Area ke stores mein pichle `days` din ka sab se zyada bikne wala maal (cache: 10 minute)."""
    key = f'reco_trend:{(area or "").strip().lower()}:{days}:{min_orders}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    from ..models import SaleOrderItem, VendorProfile
    from .views_stores import store_serves_area
    vendor_ids = [p.vendor_id for p in VendorProfile.objects.filter(is_approved=True)
                  if not area or store_serves_area(p.city, area, p.delivery_areas)]
    ids = []
    if vendor_ids:
        since = timezone.now() - timedelta(days=days)
        rows = (SaleOrderItem.objects.filter(order__order_date__gte=since, order__vendor_id__in=vendor_ids)
                .exclude(order__status='cancelled')
                .values('product_id').annotate(n=Count('order', distinct=True), q=Sum('qty'))
                .filter(n__gte=min_orders).order_by('-n', '-q')[:limit])
        ids = [r['product_id'] for r in rows]
    cache.set(key, ids, TRENDING_CACHE_SECONDS)
    return ids


def home_rows(request):
    """Shop home ke liye: {'reorder': [...], 'favourites': [...], 'trending': [...], 'area': str}. Galti par khali."""
    empty = {'reorder': [], 'favourites': [], 'trending': [], 'area': ''}
    try:
        cfg = reco_settings()
        if not cfg['enabled']:
            return empty
        from .views_customer_portal import get_delivery_area
        out = dict(empty)
        out['area'] = get_delivery_area(request) or ''
        customer = None
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and hasattr(user, 'customer_profile'):
            customer = user.customer_profile.customer
        fav_ids = []
        if customer is not None:
            out['reorder'] = reorder_cards(customer)
            fav_ids = favourite_ids(customer)
            out['favourites'] = _product_cards(fav_ids)
        shown = {c['id'] for c in out['favourites']}
        trend = [i for i in trending_ids(out['area'], cfg['days'], cfg['min_orders']) if i not in shown]
        out['trending'] = _product_cards(trend)
        return out
    except Exception:
        logger.exception('Recommendations error')
        return empty

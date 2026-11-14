"""Customer portal: pasandida stores (heart) aur wishlist (pasandida items).

- Heart sirf login customer ke liye; guest ko login page par bheja jata hai (JS 401 par).
- Admin switch: Settings > Shop > "Favourite stores and wishlist" (shop_favorites_enabled).
"""
import logging

from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..models import FavoriteStore, Product, VendorProfile, WishlistItem
from ..shop_flags import flag_required, shop_flag
from .views_customer_portal import get_cart_count_value, get_product_final_price
from .views_reviews import store_rating_map

logger = logging.getLogger(__name__)


def current_customer(request):
    """Login customer (ya None: guest / admin bina customer profile ke)."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and hasattr(user, 'customer_profile'):
        return user.customer_profile.customer
    return None


def favorite_store_ids(request):
    """Is customer ke pasandida store ids (set). Switch band ho ya guest ho to khali."""
    if not shop_flag('shop_favorites_enabled'):
        return set()
    customer = current_customer(request)
    if not customer:
        return set()
    return set(FavoriteStore.objects.filter(customer=customer).values_list('store_id', flat=True))


def wishlist_product_ids(request):
    if not shop_flag('shop_favorites_enabled'):
        return set()
    customer = current_customer(request)
    if not customer:
        return set()
    return set(WishlistItem.objects.filter(customer=customer).values_list('product_id', flat=True))


def _toggle(request, model, field, obj):
    customer = current_customer(request)
    if not customer:
        if request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Sirf customer account se heart lagta hai.'}, status=403)
        return JsonResponse({'success': False, 'login': True, 'login_url': reverse('customer_login'),
                             'message': 'Pehle login karein.'}, status=401)
    row = model.objects.filter(customer=customer, **{field: obj}).first()
    if row:
        row.delete()
        favorited = False
    else:
        row, created = model.objects.get_or_create(customer=customer, **{field: obj})
        if created and model is WishlistItem:
            from .wishlist_alerts import snapshot_for_item      # abhi ki qeemat/stock yaad rakho (alerts ke liye)
            snapshot_for_item(row)
        favorited = True
    return JsonResponse({'success': True, 'favorited': favorited})


@require_POST
@flag_required('shop_favorites_enabled', json=True)
def favorite_store_toggle(request, pk):
    store = get_object_or_404(VendorProfile, pk=pk, is_approved=True)
    return _toggle(request, FavoriteStore, 'store', store)


@require_POST
@flag_required('shop_favorites_enabled', json=True)
def wishlist_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True, approval_status='approved', vendor__isnull=False)
    return _toggle(request, WishlistItem, 'product', product)


@require_POST
@flag_required('shop_favorites_enabled', json=True)
def wishlist_alert_toggle(request, pk, kind):
    """Wishlist item ka alert chalu/band: kind = stock (Back in stock) ya price (Price drop)."""
    customer = current_customer(request)
    if not customer:
        return JsonResponse({'success': False, 'login': True, 'login_url': reverse('customer_login'),
                             'message': 'Pehle login karein.'}, status=401)
    field = {'stock': 'notify_stock', 'price': 'notify_price'}.get(kind)
    if not field:
        return JsonResponse({'success': False, 'message': 'Galat alert.'}, status=400)
    item = get_object_or_404(WishlistItem, customer=customer, product_id=pk)
    setattr(item, field, not getattr(item, field))
    item.save(update_fields=[field])
    return JsonResponse({'success': True, 'on': getattr(item, field)})


@customer_login_required
@flag_required('shop_favorites_enabled')
def favorites_page(request):
    customer = current_customer(request)
    tab = 'items' if request.GET.get('tab') == 'items' else 'stores'

    stores, items = [], []
    store_count = item_count = 0
    if customer:
        fav_qs = (FavoriteStore.objects.filter(customer=customer, store__is_approved=True)
                  .select_related('store', 'store__vendor', 'store__store_category'))
        wish_qs = (WishlistItem.objects.filter(customer=customer, product__is_active=True,
                                               product__approval_status='approved')
                   .select_related('product', 'product__vendor', 'product__unit'))
        store_count, item_count = fav_qs.count(), wish_qs.count()

        if tab == 'stores':
            ratings = store_rating_map()
            for f in fav_qs:
                st = f.store
                st.status = st.status_label
                st.is_free_delivery = (st.delivery_fee or 0) == 0
                _r = ratings.get(st.vendor_id)
                st.rating_avg = _r['avg'] if _r else None
                st.rating_count = _r['count'] if _r else 0
                stores.append(st)
        else:
            pids = [w.product_id for w in wish_qs]
            stock = dict(
                Product.objects.filter(id__in=pids).annotate(
                    ts=Coalesce(Sum('inventory__stock'), Value(0.0),
                                output_field=DecimalField(max_digits=20, decimal_places=2))
                ).values_list('id', 'ts'))
            store_names = {v: n for v, n in VendorProfile.objects.filter(
                vendor_id__in={w.product.vendor_id for w in wish_qs}).values_list('vendor_id', 'business_name')}
            wishes = list(wish_qs)
            fix_oos, fix_price = [], []
            for w in wishes:
                p = w.product
                p.final_price = get_product_final_price(p)
                p.stock_int = int(stock.get(p.id) or 0)
                p.store_name = store_names.get(p.vendor_id, '')
                p.alert_stock = w.notify_stock
                p.alert_price = w.notify_price
                items.append(p)
                # Purane wishlist items (alerts se pehle ke): halat yaad kar lo taake agla badlav pakda jaye
                if p.stock_int <= 0 and not w.was_out_of_stock:
                    fix_oos.append(w.pk)
                if w.last_price is None:
                    fix_price.append((w.pk, p.final_price))
            if fix_oos:
                WishlistItem.objects.filter(pk__in=fix_oos).update(was_out_of_stock=True)
            for wid, price in fix_price:
                WishlistItem.objects.filter(pk=wid, last_price__isnull=True).update(last_price=price)

    return render(request, 'customer_portal/favorites.html', {
        'tab': tab,
        'stores': stores,
        'items': items,
        'store_count': store_count,
        'item_count': item_count,
        'currency': 'Rs',
        'alerts_on': shop_flag('shop_wishlist_alerts_enabled'),
        'cart_count': get_cart_count_value(request),
    })

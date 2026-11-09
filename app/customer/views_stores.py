"""
Customer side: Stores list aur ek Store ki apni page (Talabat jaisi).

- store_list   : /shop/stores/            (search, store types (?type=), product category chips, Open now, Free delivery, sort)
- store_detail : /shop/stores/<id>/       (store header, category sections, +/- cart stepper, cart bar)

Sirf approved vendors (VendorProfile.is_approved) ke stores nazar aate hain, aur sirf
wahi products jo shop par live hain (approval_status='approved', is_active=True).
"""
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Max, Q, Sum, Value, When, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from ..shop_flags import flag_required, shop_flag

from ..models import Category, CompanyInfo, Product, ShopBanner, StoreCategory, VendorProfile
from .views_customer_portal import get_cart_count_value, get_delivery_area, get_product_final_price
from .views_reviews import store_rating_map, store_reviews
from .views_favorites import current_customer, favorite_store_ids
from . import coupons as coupon_logic

STATUS_ORDER = {'open': 0, 'busy': 1, 'closed': 2}


def _live_products():
    return Product.objects.filter(is_active=True, approval_status='approved', vendor__isnull=False)


def _company_name():
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


def _area_words(text):
    """'Gulberg, Lahore' -> {'gulberg', 'lahore'} (chhote/faltu lafz hata kar)."""
    out = set()
    for w in (text or '').lower().replace(',', ' ').replace('-', ' ').split():
        if len(w) >= 3:
            out.add(w)
    return out


def store_serves_area(store_city, area, delivery_areas=''):
    """
    Kya ye store customer ke "Deliver to" area mein deliver karta hai?
    - Area na ho -> True.
    - Vendor ne delivery_areas likhe hon -> wohi faisla karte hain:
        entry area mein ho ya area entry mein ho ('gulberg' in 'gulberg, lahore')  -> True.
        Customer ne sirf shehar chuna ho aur wo store ka shehar ho -> True.
    - delivery_areas khali ho -> store ke shehar se milan (shehar khali ho to True: store chhupta nahi).
    """
    if not area:
        return True
    area_l = area.lower().strip()
    entries = [e.lower() for e in VendorProfile.clean_areas(delivery_areas)]
    if entries:
        for e in entries:
            if e in area_l or area_l in e:
                return True
        return bool((store_city or '').strip()) and store_city.lower().strip() == area_l
    if not (store_city or '').strip():
        return True
    a, c = _area_words(area), _area_words(store_city)
    if a & c:
        return True
    city_l = store_city.lower().strip()
    return city_l in area_l or area_l in city_l


CURRENCY = 'Rs'           # Pakistani Rupee. Baad mein settings se lena ho to yahin badlein.

SORTS = {
    'recommended': 'Recommended',
    'rating': 'Top rated',
    'fastest': 'Fastest delivery',
    'fee': 'Lowest delivery fee',
    'min_order': 'Lowest minimum order',
}


@flag_required('shop_stores_enabled')
def store_list(request):
    search = request.GET.get('q', '').strip()[:100]
    open_only = request.GET.get('open') == '1'
    free_only = request.GET.get('free') == '1'
    deals_only = request.GET.get('deals') == '1'
    rating_min = request.GET.get('rating') == '4'          # "4+" stars
    favorites_on = shop_flag('shop_favorites_enabled')
    fav_only = favorites_on and request.GET.get('fav') == '1'
    sort = request.GET.get('sort', 'recommended')
    if sort not in SORTS:
        sort = 'recommended'
    try:
        category_id = int(request.GET.get('category', ''))
    except (TypeError, ValueError):
        category_id = None
    try:
        store_type_id = int(request.GET.get('type', ''))
    except (TypeError, ValueError):
        store_type_id = None

    live = _live_products()
    stores = VendorProfile.objects.filter(
        is_approved=True, vendor__in=live.values('vendor')
    ).select_related('vendor', 'store_category')

    # Store types (Restaurants, Grocery...) - har type mein kitne stores hain
    type_counts = dict(
        stores.exclude(store_category__isnull=True).values('store_category')
        .annotate(n=Count('id')).values_list('store_category', 'n')
    )
    store_types = list(StoreCategory.objects.filter(is_active=True))
    store_types = [t for t in store_types if type_counts.get(t.id)]
    for t in store_types:
        t.store_count = type_counts[t.id]
    if store_type_id and store_type_id not in {t.id for t in store_types}:
        store_type_id = None
    if store_type_id:
        stores = stores.filter(store_category_id=store_type_id)

    if category_id:
        stores = stores.filter(vendor__in=live.filter(category_id=category_id).values('vendor'))
    if search:
        stores = stores.filter(
            Q(business_name__icontains=search) | Q(store_description__icontains=search) |
            Q(city__icontains=search) |
            Q(vendor__in=live.filter(name__icontains=search).values('vendor'))
        )
    if free_only:
        stores = stores.filter(delivery_fee=0)

    # Deals: jin stores ke live products par discount chal raha hai (store card par "Up to N% off")
    deal_map = dict(live.filter(discount_percentage__gt=0).values('vendor')
                    .annotate(m=Max('discount_percentage')).values_list('vendor', 'm'))
    coupon_map = coupon_logic.store_offers()          # {vendor_id: live coupon} (flag OFF = khali)
    if deals_only:
        stores = stores.filter(Q(vendor_id__in=list(deal_map)) | Q(vendor_id__in=list(coupon_map)))

    # Favourites: sirf login customer ke pasandida stores
    fav_ids = favorite_store_ids(request)
    if fav_only:
        if not current_customer(request):
            return redirect(f"{reverse('customer_login')}?next={request.get_full_path()}")
        stores = stores.filter(pk__in=fav_ids)

    # Dish search: search likhne par har store ke kuch milte hue items (card par dikhane ke liye)
    matches = {}
    if search:
        for vid, pname in live.filter(name__icontains=search).order_by('name').values_list('vendor', 'name')[:400]:
            lst = matches.setdefault(vid, [])
            if len(lst) < 2:
                lst.append(pname)

    counts = dict(
        live.values('vendor').annotate(n=Count('id')).values_list('vendor', 'n')
    )
    # Har store ki top categories (card par tags ke liye): ek hi query
    tags = {}
    for vid, cname in live.exclude(category__isnull=True).values_list('vendor', 'category__name').distinct():
        tags.setdefault(vid, []).append(cname)

    stores = list(stores.order_by('business_name')[:200])
    ratings = store_rating_map()
    for st in stores:
        st.status = st.status_label
        st.product_count = counts.get(st.vendor_id, 0)
        st.tags = sorted(tags.get(st.vendor_id, []))[:3]
        st.is_free_delivery = (st.delivery_fee or 0) == 0
        _r = ratings.get(st.vendor_id)
        st.rating_avg = _r['avg'] if _r else None
        st.rating_count = _r['count'] if _r else 0
        st.max_discount = deal_map.get(st.vendor_id)
        st.offer = coupon_map.get(st.vendor_id)
        st.matched_items = matches.get(st.vendor_id, [])
        st.is_fav = st.pk in fav_ids
    if rating_min:
        stores = [s for s in stores if (s.rating_avg or 0) >= 4]
    if open_only:
        stores = [s for s in stores if s.status != 'closed']

    # ---- "Deliver to" area filter ----
    area = get_delivery_area(request)
    show_all = request.GET.get('all') == '1'
    for st in stores:
        st.in_area = store_serves_area(st.city, area, st.delivery_areas)
    outside_count = 0
    if area and not show_all:
        outside_count = sum(1 for s in stores if not s.in_area)
        stores = [s for s in stores if s.in_area]

    sort_keys = {
        'recommended': lambda s: (STATUS_ORDER[s.status], s.business_name.lower()),
        'rating': lambda s: (STATUS_ORDER[s.status], -(s.rating_avg or 0), -s.rating_count, s.business_name.lower()),
        'fastest': lambda s: (STATUS_ORDER[s.status], s.delivery_time_min, s.delivery_time_max),
        'fee': lambda s: (STATUS_ORDER[s.status], s.delivery_fee or 0),
        'min_order': lambda s: (STATUS_ORDER[s.status], s.min_order_amount or 0),
    }
    stores.sort(key=lambda s: (0 if s.in_area else 1,) + tuple(sort_keys[sort](s)))   # area wale pehle, khule pehle, band aakhir mein

    banners = list(ShopBanner.live()[:8])
    for b in banners:
        b.target = b.get_link()
    # Banner sirf pehle page par (koi search/filter na ho) - warna results ke beech mein jagah gher leta hai
    show_banners = not (search or category_id or store_type_id or open_only or free_only or deals_only or rating_min or fav_only)

    return render(request, 'customer_portal/stores.html', {
        'banners': banners if (show_banners and shop_flag('shop_banners_enabled')) else [],
        'stores': stores,
        'store_total': len(stores),
        'search': search,
        'open_only': open_only,
        'free_only': free_only,
        'deals_only': deals_only,
        'rating_min': rating_min,
        'fav_only': fav_only,
        'favorites_on': favorites_on,
        'sort': sort,
        'sorts': SORTS,
        'delivery_area': area,
        'area_filter_on': bool(area) and not show_all,
        'outside_count': outside_count,
        'selected_category': category_id,
        'store_types': store_types,
        'selected_type': store_type_id,
        'categories': Category.objects.filter(products__in=live).distinct().order_by('name'),
        'currency': CURRENCY,
        'cart_count': get_cart_count_value(request),
        'company_name': _company_name(),
    })


@flag_required('shop_stores_enabled')
def store_detail(request, pk):
    store = get_object_or_404(VendorProfile.objects.select_related('vendor', 'store_category'), pk=pk, is_approved=True)
    base = _live_products().filter(vendor=store.vendor)

    search = request.GET.get('q', '').strip()[:100]
    try:
        category_id = int(request.GET.get('category', ''))
    except (TypeError, ValueError):
        category_id = None

    # Sections ki tarteeb: vendor ki tay ki hui (StoreMenuSection), baqi aakhir mein naam se
    from ..models import StoreMenuSection
    section_order = dict(StoreMenuSection.objects.filter(store=store).values_list('category_id', 'sort_order'))
    big = 10 ** 6
    menu = list(base.values('category_id', 'category__name').annotate(n=Count('id')))
    menu.sort(key=lambda m: (section_order.get(m['category_id'], big), (m['category__name'] or '').lower()))
    if section_order:
        section_rank = Case(
            *[When(category_id=cid, then=Value(rank)) for cid, rank in section_order.items()],
            default=Value(big), output_field=IntegerField())
    else:
        section_rank = Value(big, output_field=IntegerField())

    products = base.select_related('category', 'unit').annotate(
        total_stock=Coalesce(Sum('inventory__stock'), Value(0.0),
                             output_field=DecimalField(max_digits=20, decimal_places=2))
    )
    if category_id:
        products = products.filter(category_id=category_id)
    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search))

    products = products.annotate(section_rank=section_rank)
    page_obj = Paginator(products.order_by('section_rank', 'category__name', 'name'), 24).get_page(
        request.GET.get('page', 1))

    # Popular section: sirf pehle page par, bina search/category filter ke
    popular = []
    if not search and not category_id and page_obj.number == 1:
        popular = list(base.filter(is_popular=True).select_related('category', 'unit').annotate(
            total_stock=Coalesce(Sum('inventory__stock'), Value(0.0),
                                 output_field=DecimalField(max_digits=20, decimal_places=2))
        ).order_by('name')[:8])

    # Cart ki halat (sirf is store ka maal): page par +/- stepper aur neeche cart bar ke liye
    cart = request.session.get('cart', {})
    cart_state = {}
    for key, item in cart.items():
        if (item.get('vendor_id') or 0) == store.vendor_id:
            cart_state[str(key)] = {'qty': int(item.get('quantity', 0) or 0), 'price': float(item.get('price', 0) or 0)}
    from ..models import ProductOptionGroup
    option_pids = set(ProductOptionGroup.objects.filter(
        product__in=list(page_obj) + popular, is_active=True).values_list('product_id', flat=True))
    for p in list(page_obj) + popular:
        p.has_options = p.id in option_pids   # size / extras wala product: card se nahi, product page se
        p.final_price = get_product_final_price(p)
        p.has_discount = bool(p.discount_percentage and p.discount_percentage > 0)
        p.old_price = None
        if p.has_discount and p.discount_percentage < 100:
            try:
                p.old_price = (Decimal(p.final_price) / (Decimal(1) - Decimal(p.discount_percentage) / Decimal(100))
                               ).quantize(Decimal('0.001'))
            except Exception:
                p.old_price = None
        p.cart_qty = cart_state.get(str(p.id), {}).get('qty', 0)
        p.in_cart = p.cart_qty > 0
        p.stock_int = int(p.total_stock or 0)

    favorites_on = shop_flag('shop_favorites_enabled')
    is_fav = favorites_on and store.pk in favorite_store_ids(request)
    store_offer = coupon_logic.store_offers().get(store.vendor_id)

    return render(request, 'customer_portal/store_detail.html', {
        'reviews': store_reviews(store.vendor),
        'store': store,
        'status': store.status_label,
        'products': page_obj,
        'popular': popular,
        'favorites_on': favorites_on,
        'is_fav': is_fav,
        'store_offer': store_offer,
        'page_obj': page_obj,
        'menu': menu,
        'menu_total': sum(m['n'] for m in menu),
        'store_tags': [m['category__name'] for m in menu if m['category__name']][:3],
        'search': search,
        'selected_category': category_id,
        'currency': CURRENCY,
        'cart_state': cart_state,
        'cart_other': bool(cart) and not cart_state,
        'cart_count': get_cart_count_value(request),
        'company_name': _company_name(),
    })

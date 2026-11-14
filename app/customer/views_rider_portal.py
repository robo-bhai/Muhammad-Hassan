"""
Rider system (Talabat jaisa).

Rider:  login -> Online -> "Naye orders" (offers) mein se Accept (jo pehle accept kare uska) ->
        Maal le liya -> Deliver ho gaya (COD cash + kamai darj) ; History, Earnings.
Vendor: Ready karne ke baad khud rider chun sakta hai ya offers se koi rider le leta hai.
Admin:  riders banata/band karta hai, fee set karta hai, rider ka cash jama / kamai ki ada'egi darj karta hai.
"""
import logging
from functools import wraps

from django.conf import settings
from .vendor_access import get_vendor_profile
from django.contrib import messages
from django.contrib.auth import authenticate, logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from ..shop_flags import flag_required, shop_flag
from django.utils import timezone
from urllib.parse import quote
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import (
    CompanyInfo, DeliveryInfo, OrderTracking, RiderBonus, RiderProfile, RiderSettlement, SaleOrder, VendorProfile,
)
from . import store_orders
from ..utils.password_policy import first_error
from . import dispatch
from . import batching
from . import demand
from . import goals
from . import rider_gate
from .views_reviews import rider_rating
from .views_customer_auth import get_client_ip, is_valid_phone, normalize_phone, safe_login

logger = logging.getLogger(__name__)

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 10 * 60

ACTIVE_STATUSES = ['assigned', 'picked_up', 'in_transit']
MAX_ACTIVE_ORDERS = 3          # ek rider ek waqt mein itne orders tak


# ============================================
# HELPERS
# ============================================

def _company_name():
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


def rider_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, '🔒 Please log in as a rider first')
            return redirect('rider_login')
        profile = getattr(request.user, 'rider_profile', None)
        if profile is None:
            messages.error(request, '❌ This page is for riders only')
            return redirect('shop_home')
        if not profile.is_active:
            logout(request)
            messages.error(request, '❌ Your rider account is disabled. Please contact the admin.')
            return redirect('rider_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def _track(order, status, title, description, user, rider=None):
    OrderTracking.objects.create(
        sale_order=order, status=status, title=title, description=description,
        rider_name=getattr(rider, 'name', None), rider_contact=getattr(rider, 'phone', None),
        updated_by=user,
    )


def _vendor_user(order):
    if not order.vendor_id:
        return None
    vp = VendorProfile.objects.filter(vendor_id=order.vendor_id).select_related('user').first()
    return vp.user if vp else None



# ============================================
# CALCULATIONS
# ============================================

def _D(v):
    return Decimal(v or 0)


def rider_balances(rider):
    """Cash jo rider ke paas hai aur kamai jo usay milni hai."""
    d = DeliveryInfo.objects.filter(rider=rider, status='delivered').aggregate(
        cash=Sum('cash_collected'), earned=Sum('rider_fee'), n=Count('id'))
    st = {r['kind']: _D(r['t']) for r in rider.settlements.values('kind').annotate(t=Sum('amount'))}
    cash, fees = _D(d['cash']), _D(d['earned'])
    bonus = _D(rider.bonuses.aggregate(t=Sum('amount'))['t'])
    earned = fees + bonus
    return {
        'bonus': bonus, 'fees': fees,
        'deliveries': d['n'] or 0,
        'cash_collected': cash,
        'cash_deposited': st.get('cash_in', Decimal('0')),
        'cash_in_hand': cash - st.get('cash_in', Decimal('0')),
        'earned': earned,
        'paid_out': st.get('payout', Decimal('0')),
        'due': earned - st.get('payout', Decimal('0')),
    }


def period_stats(rider, since_date):
    a = DeliveryInfo.objects.filter(rider=rider, status='delivered', delivered_at__date__gte=since_date)\
        .aggregate(n=Count('id'), earned=Sum('rider_fee'))
    return {'deliveries': a['n'] or 0, 'earned': _D(a['earned'])}


def _setting_num(name):
    from .offers import setting_decimal
    return setting_decimal(name, '0')


def _goal_cfg():
    return {
        'daily': (int(_setting_num('rider_goal_daily_orders')), _setting_num('rider_goal_daily_bonus')),
        'weekly': (int(_setting_num('rider_goal_weekly_orders')), _setting_num('rider_goal_weekly_bonus')),
    }


def _goal_periods():
    today = timezone.localdate()
    return {'daily': today, 'weekly': goals.week_start(today)}


def _goals_ctx(rider):
    """Rider ke goals ki progress: [{'kind','label','done','goal','bonus','pct','left','reached','paid'}]."""
    out = []
    periods = _goal_periods()
    cfg = _goal_cfg()
    labels = {'daily': 'Aaj ka goal', 'weekly': 'Is hafte ka goal'}
    for kind in ('daily', 'weekly'):
        goal, bonus = cfg[kind]
        p = goals.progress(period_stats(rider, periods[kind])['deliveries'], goal, bonus)
        if not p:
            continue
        p.update(kind=kind, label=labels[kind],
                 paid=rider.bonuses.filter(kind=kind, period_start=periods[kind]).exists())
        out.append(p)
    return out


def _award_goal_bonuses(rider):
    """Delivery ke baad: jo goal poora hua aur bonus abhi nahi mila, woh de do. Naye bonuses ki list lautata hai."""
    given = []
    periods = _goal_periods()
    for kind, (goal, bonus) in _goal_cfg().items():
        if goal <= 0 or bonus <= 0:
            continue
        n = period_stats(rider, periods[kind])['deliveries']
        if n < goal:
            continue
        _obj, created = RiderBonus.objects.get_or_create(
            rider=rider, kind=kind, period_start=periods[kind],
            defaults={'amount': bonus, 'deliveries': n})
        if created:
            given.append((kind, bonus))
    return given


def _cash_ctx(rider, balances=None):
    b = balances or rider_balances(rider)
    return goals.cash_state(b['cash_in_hand'], _setting_num('rider_cash_limit'))


def _touch(rider):
    RiderProfile.objects.filter(pk=rider.pk).update(last_seen_at=now())


def _maps(addr):
    return 'https://www.google.com/maps/search/?api=1&query=' + quote(addr) if addr else ''


def _nav_links(lat, lng, addr):
    """Google Maps / Waze ke turn-by-turn navigation links. Coordinates ko tarjih, warna address."""
    if lat is not None and lng is not None:
        dest = f'{lat},{lng}'
        return {
            'google': f'https://www.google.com/maps/dir/?api=1&destination={dest}&travelmode=two-wheeler&dir_action=navigate',
            'waze': f'https://waze.com/ul?ll={dest}&navigate=yes',
        }
    if addr:
        q = quote(addr)
        return {
            'google': f'https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=two-wheeler&dir_action=navigate',
            'waze': f'https://waze.com/ul?q={q}&navigate=yes',
        }
    return None


def _nav_for_leg(di, o, store_addr, cust_addr):
    """Rider ab kahan ja raha hai: 'assigned' = store, uske baad = customer."""
    if di.status == 'assigned':
        s_lat, s_lng = dispatch._store_coords(o)
        links = _nav_links(s_lat, s_lng, store_addr)
        return ('store', links) if links else (None, None)
    links = _nav_links(o.delivery_lat, o.delivery_lng, cust_addr)
    return ('customer', links) if links else (None, None)


def _card(di):
    o = di.sale_order
    cust = o.customer
    store_addr = getattr(o.vendor, 'address', '') if o.vendor_id else ''
    phone = (getattr(cust, 'contact_number', '') or '')
    digits = ''.join(ch for ch in phone if ch.isdigit())
    cust_addr = getattr(cust, 'address', '') or ''
    nav_leg, nav = _nav_for_leg(di, o, store_addr, cust_addr)
    return {
        'nav_leg': nav_leg, 'nav': nav,
        'di': di, 'order': o, 'items': list(o.items.all()),
        'store': store_orders.store_name(o.vendor_id),
        'store_phone': getattr(o.vendor, 'contact_number', '') if o.vendor_id else '',
        'store_addr': store_addr, 'map_store': _maps(store_addr),
        'cust_addr': getattr(cust, 'address', '') or '', 'map_cust': _maps(getattr(cust, 'address', '') or ''),
        'map_pin': (f'https://www.google.com/maps/dir/?api=1&destination={o.delivery_lat},{o.delivery_lng}'
                    if o.delivery_lat is not None and o.delivery_lng is not None else ''),
        'cust_phone': phone, 'wa_cust': f'https://wa.me/{digits}' if digits else '',
        'total': store_orders.order_cash_due(o),
        'is_cod': (o.payment_method or 'cod') == 'cod',
    }


def _offers_qs():
    """Ready orders jinka abhi koi rider nahi."""
    taken = DeliveryInfo.objects.filter(rider__isnull=False, sale_order__isnull=False).values('sale_order_id')
    return (SaleOrder.objects.filter(status='ready', vendor__isnull=False)
            .exclude(pk__in=taken).select_related('customer', 'vendor')
            .prefetch_related('items__product').order_by('vendor_responded_at')[:20])


def _ll(lat, lng):
    return (float(lat), float(lng)) if lat is not None and lng is not None else None


def _batch_info(o):
    """Order ki batching ke liye zaroori maloomat."""
    s_lat, s_lng = dispatch._store_coords(o)
    cust = o.customer
    return {
        'order_no': o.order_no, 'vendor_id': o.vendor_id,
        'store_name': store_orders.store_name(o.vendor_id),
        'store_ll': _ll(s_lat, s_lng),
        'store_addr': getattr(o.vendor, 'address', '') if o.vendor_id else '',
        'cust_name': getattr(cust, 'name', '') or '',
        'drop_ll': _ll(o.delivery_lat, o.delivery_lng),
        'cust_addr': getattr(cust, 'address', '') or '',
    }


BATCH_LABELS = {
    'same_store': '🔗 Aap ke order wale hi store ka — saath uthayein',
    'near_store': '🔗 Aap ke order ke store ke qareeb — saath uthayein',
    'same_area': '🔗 Aap ke customer ke ilaqe mein — ek hi raaste par',
}


def _offer_card(o, rider, actives=None):
    cust = o.customer
    store_addr = getattr(o.vendor, 'address', '') if o.vendor_id else ''
    return {
        'order': o, 'items_count': sum(1 for _ in o.items.all()),
        'store': store_orders.store_name(o.vendor_id), 'store_addr': store_addr,
        'cust_addr': getattr(cust, 'address', '') or '',
        'total': store_orders.order_cash_due(o),
        'is_cod': (o.payment_method or 'cod') == 'cod',
        'fee': rider.per_delivery_fee,
        'dist_km': dispatch.distance_km(o, rider),
        'batch': BATCH_LABELS.get(batching.match_offer(_batch_info(o), actives or [])),
    }


def _assign(order, di, rider, user):
    """Rider ko order do (vendor ke chunne par ya rider ke accept karne par)."""
    di.delivery_type = 'local_rider'
    di.rider = rider
    di.rider_name = rider.name
    di.rider_contact = rider.phone
    di.rider_vehicle = rider.vehicle
    di.status = 'assigned'
    di.assigned_at = now()
    di.created_by = user
    di.save()
    _track(order, 'rider_assigned', 'Rider Assigned', f'Rider: {rider.name} ({rider.phone})', user, rider)
    store_orders._notify(store_orders._customer_user(order),
                         f'🏍️ Order #{order.order_no}: rider mil gaya',
                         f'Rider {rider.name} ({rider.phone}) aap ka order lene aa raha hai.',
                         f'/shop/order/{order.id}/', 'info')
    store_orders._notify(_vendor_user(order), f'🏍️ Order #{order.order_no}: rider {rider.name} aa raha hai',
                         f'{rider.name} ({rider.phone}) maal lene aa raha hai.',
                         '/shop/vendor/orders/?tab=active', 'info')


# ============================================
# RIDER LOGIN / LOGOUT
# ============================================

@flag_required('rider_login_enabled', redirect_to='shop_home')
def rider_login(request):
    if request.user.is_authenticated and hasattr(request.user, 'rider_profile'):
        return redirect('rider_home')

    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        password = request.POST.get('password', '')
        if not phone_raw or not password:
            messages.error(request, '❌ Enter both phone and password')
            return redirect('rider_login')

        phone = normalize_phone(phone_raw)
        key = f"rider_login:{phone}:{get_client_ip(request) or ''}"
        if cache.get(key, 0) >= LOGIN_MAX_ATTEMPTS:
            messages.error(request, '🔒 Too many attempts. Please try again after 10 minutes.')
            return redirect('rider_login')

        rider = RiderProfile.objects.select_related('user').filter(phone=phone, is_active=True).first()
        user = authenticate(request, username=rider.user.username, password=password) if rider else None
        if not rider:
            waiting = RiderProfile.objects.select_related('user').filter(phone=phone, is_active=False).first()
            if waiting and authenticate(request, username=waiting.user.username, password=password):
                messages.info(request, '⏳ Your registration is waiting for admin approval.')
                return redirect('rider_login')
        if not user:
            cache.set(key, cache.get(key, 0) + 1, LOGIN_LOCK_SECONDS)
            messages.error(request, '❌ Phone or password is incorrect')
            return redirect('rider_login')

        cache.delete(key)
        safe_login(request, user)
        request.session.save()
        rider.last_login_at = now()
        rider.save(update_fields=['last_login_at'])
        return redirect('rider_home')

    return render(request, 'customer_portal/rider/login.html', {'company_name': _company_name()})


@flag_required('rider_register_enabled', redirect_to='shop_home')
def rider_register(request):
    """Rider khud register kare. Admin approval ke baghair login nahi (jab tak 'Auto-approve new riders' OFF ho)."""
    if request.user.is_authenticated and hasattr(request.user, 'rider_profile'):
        return redirect('rider_home')

    form = {}
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:100]
        phone_raw = request.POST.get('phone', '').strip()[:20]
        vehicle = request.POST.get('vehicle', '').strip()[:50]
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm', '')
        form = {'name': name, 'phone': phone_raw, 'vehicle': vehicle}
        key = 'rider_register:%s' % (get_client_ip(request) or '')

        error = None
        if cache.get(key, 0) >= 5:
            error = '🔒 Too many registrations. Please try again later.'
        elif not name or not phone_raw:
            error = '❌ Naam aur phone likhein.'
        elif not is_valid_phone(phone_raw):
            error = '❌ Phone number is not valid.'
        elif first_error(password, (name, phone_raw)):
            error = '❌ ' + first_error(password, (name, phone_raw))
        elif password != confirm:
            error = '❌ Both passwords must be the same.'

        if not error:
            phone = normalize_phone(phone_raw)
            username = 'rider_' + phone.replace('+', '')
            docs_flow = shop_flag('rider_documents_required')     # documents upload + approval (Talabat jaisa)
            auto = True if docs_flow else shop_flag('rider_auto_approve')
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=username, password=password, first_name=name[:30])
                    RiderProfile.objects.create(user=user, name=name, phone=phone, vehicle=vehicle, is_active=auto,
                                                approval_status='pending' if docs_flow else 'approved')
            except IntegrityError:
                error = '❌ A rider with this phone already exists.'
            else:
                cache.set(key, cache.get(key, 0) + 1, 3600)
                if docs_flow:
                    messages.success(request, '✅ Registration complete. Log in and upload your documents (CPR, licence, vehicle, photo) for approval.')
                elif auto:
                    messages.success(request, '✅ Registration complete. You can log in now.')
                else:
                    messages.success(request, '✅ Registration received. You can log in after admin approval.')
                return redirect('rider_login')
        messages.error(request, error)

    return render(request, 'customer_portal/rider/register.html', {'company_name': _company_name(), 'form': form})


def rider_logout(request):
    rp = getattr(request.user, 'rider_profile', None) if request.user.is_authenticated else None
    if rp:
        RiderProfile.objects.filter(pk=rp.pk).update(is_online=False)
    request.session.flush()
    logout(request)
    messages.success(request, '👋 You have been logged out.')
    return redirect('rider_login')


# ============================================
# RIDER SCREENS
# ============================================

def _dispute_pending(rider):
    from .disputes import needs_response_count
    return needs_response_count('rider', rider)


def _rider_ctx(request, nav, **extra):
    rider = request.user.rider_profile
    ctx = {'rider': rider, 'nav': nav, 'company_name': _company_name(),
           'active_count': DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES).count(),
           'dispute_count': _dispute_pending(rider)}
    ctx.update(extra)
    return ctx


@rider_login_required
def rider_home(request):
    rider = request.user.rider_profile
    _touch(rider)
    mine = (DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES, sale_order__isnull=False)
            .select_related('sale_order', 'sale_order__customer', 'sale_order__vendor')
            .prefetch_related('sale_order__items__product').order_by('assigned_at'))
    actives = [_batch_info(d.sale_order) for d in mine]
    can_work, gate_msg = rider_gate.work_status(rider)
    offers = [_offer_card(o, rider, actives) for o in dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES)] if (rider.is_online and can_work) else []
    # ek raaste ke offers pehle
    offers.sort(key=lambda c: 0 if c['batch'] else 1)
    plan = batching.plan_route(
        [dict(a, status=d.status) for a, d in zip(actives, mine)],
        dispatch._rider_coords(rider, now()) if actives else None)
    today = period_stats(rider, timezone.localdate())
    bal = rider_balances(rider)
    return render(request, 'customer_portal/rider/home.html', _rider_ctx(
        request, 'orders', mine=[_card(d) for d in mine], offers=offers, plan=plan,
        today=today, balances=bal, max_active=MAX_ACTIVE_ORDERS,
        goal_list=_goals_ctx(rider), cash=_cash_ctx(rider, bal),
        gate_msg=gate_msg, doc_warnings=rider_gate.doc_warnings(rider), next_shift=rider_gate.next_shift(rider)))


DEMAND_CACHE_SECONDS = 300


def _demand_rows():
    """Pichle 28 din ke delivery orders: [(weekday, hour, vendor_id)]. 5 minute cache (sab riders ke liye ek)."""
    key = 'rider_demand_rows_v1'
    rows = cache.get(key)
    if rows is not None:
        return rows
    since = now() - timedelta(days=demand.WINDOW_DAYS)
    qs = (SaleOrder.objects.filter(created_at__gte=since, delivery_info__isnull=False)
          .exclude(status='cancelled').values_list('created_at', 'vendor_id')[:20000])
    rows = []
    for dt, vid in qs:
        loc = timezone.localtime(dt)
        rows.append((loc.weekday(), loc.hour, vid))
    cache.set(key, rows, DEMAND_CACHE_SECONDS)
    return rows


@rider_login_required
@flag_required('rider_hotspots_enabled', redirect_to='rider_home')
def rider_hotspots(request):
    """Heat map (kahan orders zyada hain) + shift planner (kab kaam karna behtar hai)."""
    rider = request.user.rider_profile
    _touch(rider)
    rows = _demand_rows()
    vids = {v for _w, _h, v in rows if v}
    stores = {}
    for p in VendorProfile.objects.filter(vendor_id__in=vids).values('vendor_id', 'business_name', 'lat', 'lng'):
        stores[p['vendor_id']] = {'name': p['business_name'], 'lat': _f(p['lat']), 'lng': _f(p['lng'])}

    local = timezone.localtime()
    wd, hr = local.weekday(), local.hour
    near_hours = {hr, (hr + 1) % 24, (hr + 2) % 24}
    today_profile = demand.hour_profile(rows, wd)
    data = {
        'zones_now': demand.zones(rows, stores, hours=near_hours, weekday=wd),
        'zones_day': demand.zones(rows, stores, weekday=wd),
        'zones_all': demand.zones(rows, stores),
        'profile': today_profile, 'hour': hr,
        'my': ([float(rider.last_lat), float(rider.last_lng)]
               if rider.last_lat is not None and rider.last_lng is not None else None),
    }
    return render(request, 'customer_portal/rider/hotspots.html', _rider_ctx(
        request, 'hotspots', data=data, today_name=demand.DAY_NAMES[wd],
        plan=demand.weekly_plan(rows), today_window=demand.best_window(today_profile),
        has_data=bool(rows), has_zones=bool(data['zones_all']), max_hour=max(today_profile) or 1))


def _f(v):
    return float(v) if v is not None else None


@rider_login_required
def rider_history(request):
    rider = request.user.rider_profile
    qs = (DeliveryInfo.objects.filter(rider=rider, status__in=['delivered', 'cancelled'], sale_order__isnull=False)
          .select_related('sale_order', 'sale_order__customer', 'sale_order__vendor')
          .order_by('-delivered_at', '-assigned_at')[:50])
    rows = [{'di': d, 'order': d.sale_order, 'store': store_orders.store_name(d.sale_order.vendor_id),
             'total': store_orders.order_cash_due(d.sale_order)} for d in qs]
    return render(request, 'customer_portal/rider/history.html', _rider_ctx(request, 'history', rows=rows))


@rider_login_required
@flag_required('rider_earnings_enabled', redirect_to='rider_home')
def rider_earnings(request):
    rider = request.user.rider_profile
    today = timezone.localdate()
    return render(request, 'customer_portal/rider/earnings.html', _rider_ctx(
        request, 'earnings',
        b=rider_balances(rider),
        today=period_stats(rider, today),
        week=period_stats(rider, today - timedelta(days=6)),
        rating=rider_rating(rider),
        goal_list=_goals_ctx(rider), cash=_cash_ctx(rider),
        bonuses=list(rider.bonuses.all()[:10]),
        settlements=list(rider.settlements.all()[:20])))


@rider_login_required
@require_POST
def rider_toggle_online(request):
    rider = request.user.rider_profile
    if not rider.is_online:                       # Online jaane se pehle approval / documents / shift check
        ok, why = rider_gate.work_status(rider)
        if not ok:
            messages.error(request, why)
            return redirect('rider_documents' if rider.approval_status != 'approved' else 'rider_home')
    rider.is_online = not rider.is_online
    rider.last_seen_at = now()
    rider.save(update_fields=['is_online', 'last_seen_at'])
    messages.success(request, '🟢 You are online. New order offers will appear.' if rider.is_online
                     else '⚫ You are offline. You will not get new offers.')
    return redirect('rider_home')


@rider_login_required
def rider_poll(request):
    """Har ~12 second mein: naye offers/orders ka count (awaaz ke liye)."""
    rider = request.user.rider_profile
    _touch(rider)
    visible = dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES) if (rider.is_online and rider_gate.work_status(rider)[0]) else []
    active = DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES).count()
    assigned = DeliveryInfo.objects.filter(rider=rider, status='assigned').count()
    alerts = []
    if visible and shop_flag('rider_offer_alert_enabled') and shop_flag('rider_can_accept_orders'):
        for o in visible[:3]:      # full-screen alert: sab se purane 3 offers
            c = _offer_card(o, rider)
            alerts.append({
                'id': o.id, 'order_no': str(o.order_no), 'store': c['store'], 'store_addr': c['store_addr'],
                'cust_addr': c['cust_addr'], 'fee': f'{c["fee"]:,.0f}', 'is_cod': c['is_cod'],
                'total': f'{c["total"]:,.0f}', 'dist_km': c['dist_km'], 'items': c['items_count'],
                'accept_url': reverse('rider_accept_order', args=[o.id]),
                'decline_url': reverse('rider_decline_order', args=[o.id]),
            })
    return JsonResponse({'offers': len(visible), 'active': active, 'assigned': assigned, 'online': rider.is_online,
                         'offer_list': alerts, 'alert_seconds': dispatch.WINDOW_SECONDS})


@rider_login_required
@flag_required('rider_can_accept_orders', redirect_to='rider_home')
@require_POST
def rider_accept_order(request, pk):
    """Offer accept: jo pehle accept kare usay order milta hai."""
    rider = request.user.rider_profile
    if not rider.is_online:
        messages.error(request, '❌ Please go online first.')
        return redirect('rider_home')
    ok, why = rider_gate.work_status(rider)
    if not ok:
        messages.error(request, why)
        return redirect('rider_home')
    if DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES).count() >= MAX_ACTIVE_ORDERS:
        messages.error(request, f'❌ You already have {MAX_ACTIVE_ORDERS} orders. Please complete them first.')
        return redirect('rider_home')

    try:
        with transaction.atomic():
            order = SaleOrder.objects.select_for_update().filter(pk=pk, status='ready').first()
            if not order:
                raise store_orders.OrderActionError('Ye order ab available nahi.')
            if not dispatch.can_take(order, rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES):
                raise store_orders.OrderActionError('This order is being offered to another rider right now. Please check again shortly.')
            di, _ = DeliveryInfo.objects.select_for_update().get_or_create(sale_order=order)
            if di.rider_id and di.status != 'cancelled':
                raise store_orders.OrderActionError('Ye order kisi aur rider ne le liya.')
            _assign(order, di, rider, request.user)
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
        return redirect('rider_home')

    messages.success(request, f'✅ Order #{order.order_no} is yours. Now pick up the items from {store_orders.store_name(order.vendor_id)}.')
    return redirect('rider_home')


MAX_PROOF_BYTES = 8 * 1024 * 1024


def _clean_proof_photo(f):
    """Delivery photo check: sirf asli tasveer, 8 MB tak. Galat ho to OrderActionError."""
    if not f:
        return None
    if f.size > MAX_PROOF_BYTES:
        raise store_orders.OrderActionError('Photo bohat bari hai (max 8 MB).')
    try:
        from PIL import Image
        img = Image.open(f)
        img.verify()
        fmt = (img.format or '').upper()
        f.seek(0)
    except Exception:
        raise store_orders.OrderActionError('Yeh file tasveer nahi hai. Dobara photo lein.')
    if fmt not in ('JPEG', 'PNG', 'WEBP', 'MPO'):
        raise store_orders.OrderActionError('Sirf JPG, PNG ya WebP photo chalti hai.')
    return f


@rider_login_required
@require_POST
def rider_order_action(request, pk, action):
    """action: pickup | deliver"""
    rider = request.user.rider_profile
    if action not in ('pickup', 'deliver'):
        messages.error(request, '❌ Invalid action.')
        return redirect('rider_home')

    try:
        with transaction.atomic():
            order = get_object_or_404(SaleOrder.objects.select_for_update(), pk=pk)
            di = get_object_or_404(DeliveryInfo, sale_order=order, rider=rider)
            cust = store_orders._customer_user(order)
            shop = store_orders.store_name(order.vendor_id)

            if action == 'pickup':
                if di.status != 'assigned' or order.status != 'ready':
                    raise store_orders.OrderActionError('This order is no longer ready for pickup.')
                di.status = 'picked_up'
                di.picked_up_at = now()
                di.save()
                _track(order, 'out_for_delivery', 'Out for Delivery',
                       f'Rider {rider.name} ne {shop} se maal le liya.', request.user, rider)
                from . import whatsapp_auto
                whatsapp_auto.notify(order, 'pickup', rider=rider)
                store_orders._notify(cust, f'🛵 Order #{order.order_no} raaste mein hai',
                                     f'Rider {rider.name} ({rider.phone}) aap ka order le kar nikal chuka hai.',
                                     f'/shop/order/{order.id}/', 'info')
                messages.success(request, f'📦 Order #{order.order_no}: items picked up. Now go to the customer.')
            else:
                if di.status not in ('picked_up', 'in_transit') or order.status != 'ready':
                    raise store_orders.OrderActionError('Pehle "Maal le liya" dabayein.')
                proof = _clean_proof_photo(request.FILES.get('proof_photo'))
                if proof is None and shop_flag('rider_proof_photo_required'):
                    raise store_orders.OrderActionError('Deliver karne se pehle delivery ki photo lagana zaroori hai.')
                if proof is not None:
                    di.delivery_photo = proof
                di.delivery_signature = (request.POST.get('receiver_name') or '').strip()[:100] or None
                total = store_orders.order_cash_due(order)
                is_cod = (order.payment_method or 'cod') == 'cod'
                di.status = 'delivered'
                di.delivered_at = now()
                di.rider_fee = rider.per_delivery_fee
                di.cash_collected = total if is_cod else Decimal('0')
                di.delivery_notes = (f'COD cash rider ne liya: Rs. {total:,.0f}' if is_cod
                                     else 'Online payment - cash nahi liya')
                di.save()
                store_orders.apply_vendor_action(order, 'delivered', user=request.user)
                _track(order, 'delivered', 'Delivered',
                       f'Rider {rider.name} ne order deliver kar diya.', request.user, rider)
                store_orders._notify(_vendor_user(order), f'🎉 Order #{order.order_no} deliver ho gaya',
                                     f'Rider {rider.name} ne deliver kar diya.'
                                     + (f' COD Rs. {total:,.0f} rider ke paas hai.' if is_cod else ''),
                                     '/shop/vendor/orders/?tab=done', 'success')
                msg = f'🎉 Order #{order.order_no} deliver ho gaya. Kamai: Rs. {rider.per_delivery_fee:,.0f}.'
                for kind, amt in _award_goal_bonuses(rider):
                    msg += f' 🏆 {"Daily" if kind == "daily" else "Weekly"} goal poora! Bonus: Rs. {amt:,.0f}.'
                    store_orders._notify(request.user, '🏆 Goal bonus mila',
                                         f'{"Daily" if kind == "daily" else "Weekly"} goal poora karne par Rs. {amt:,.0f} bonus.',
                                         reverse('rider_earnings'), 'success')
                if is_cod:
                    msg += f' Customer se Rs. {total:,.0f} cash liya — admin ko jama karwayein.'
                messages.success(request, msg)
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
    return redirect('rider_home')


# ============================================
# VENDOR: rider chunna
# ============================================

@vendor_login_required
@flag_required('vendor_can_assign_riders', redirect_to='vendor_orders')
@require_POST
def vendor_assign_rider(request, pk):
    vendor = get_vendor_profile(request.user).vendor
    rider = get_object_or_404(RiderProfile, pk=request.POST.get('rider_id') or 0, is_active=True, approval_status='approved')

    try:
        with transaction.atomic():
            order = get_object_or_404(SaleOrder.objects.select_for_update(), pk=pk, vendor=vendor)
            if order.status != 'ready':
                raise store_orders.OrderActionError('Rider sirf "Ready" order par chun sakte hain.')
            di, _ = DeliveryInfo.objects.select_for_update().get_or_create(sale_order=order)
            if di.status in ('picked_up', 'in_transit', 'delivered'):
                raise store_orders.OrderActionError('The rider has already picked up the order, so it cannot be changed now.')
            _assign(order, di, rider, request.user)
            store_orders._notify(rider.user, f'🏍️ Naya order #{order.order_no}',
                                 f'{store_orders.store_name(order.vendor_id)} se maal uthana hai.',
                                 reverse('rider_home'), 'info')
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
        return redirect(f"{reverse('vendor_orders')}?tab=active")

    messages.success(request, f'🏍️ Order #{order.order_no}: assigned to rider {rider.name}.')
    return redirect(f"{reverse('vendor_orders')}?tab=active")


# ============================================
# ADMIN: riders manage + hisab
# ============================================

def _admin_only(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")
        if not request.user.is_superuser:
            messages.error(request, '❌ Only the admin can manage riders.')
            return redirect('shop_home')
        return view(request, *args, **kwargs)
    return wrapper


def _money(raw):
    try:
        v = Decimal(str(raw).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None
    return v.quantize(Decimal('0.01')) if v >= 0 else None


@_admin_only
def rider_manage(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()[:100]
            phone_raw = request.POST.get('phone', '').strip()[:20]
            password = request.POST.get('password', '')
            vehicle = request.POST.get('vehicle', '').strip()[:50]
            fee = _money(request.POST.get('fee', '50'))
            if not name or not phone_raw or fee is None:
                messages.error(request, '❌ Enter name, phone, fee and password.')
            elif first_error(password, (name, phone_raw)):
                messages.error(request, '❌ ' + first_error(password, (name, phone_raw)))
            elif not is_valid_phone(phone_raw):
                messages.error(request, '❌ Phone number is not valid.')
            else:
                phone = normalize_phone(phone_raw)
                username = 'rider_' + phone.replace('+', '')
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(username=username, password=password, first_name=name[:30])
                        RiderProfile.objects.create(user=user, name=name, phone=phone, vehicle=vehicle,
                                                    per_delivery_fee=fee)
                    messages.success(request, f'✅ Rider {name} created. Login: {phone}')
                except IntegrityError:
                    messages.error(request, '❌ A rider with this phone already exists.')
        elif action == 'toggle':
            r = get_object_or_404(RiderProfile, pk=request.POST.get('rider_id') or 0)
            r.is_active = not r.is_active
            if not r.is_active:
                r.is_online = False
            r.save(update_fields=['is_active', 'is_online'])
            messages.success(request, f'{"✅ Chalu" if r.is_active else "⏸️ Band"}: {r.name}')
        elif action == 'password':
            r = get_object_or_404(RiderProfile, pk=request.POST.get('rider_id') or 0)
            pw = request.POST.get('password', '')
            if first_error(pw, (r.name, r.phone)):
                messages.error(request, '❌ ' + first_error(pw, (r.name, r.phone)))
            else:
                r.user.set_password(pw)
                r.user.save()
                messages.success(request, f'🔑 Password changed for {r.name}.')
        return redirect('rider_manage')

    riders = list(RiderProfile.objects.all())
    online_cut = now() - timedelta(minutes=2)
    for r in riders:
        r.open_count = r.deliveries.filter(status__in=ACTIVE_STATUSES).count()
        r.bal = rider_balances(r)
        r.live = bool(r.is_online and r.last_seen_at and r.last_seen_at >= online_cut)
        r.rating = rider_rating(r)
        r.pending_docs = r.documents.filter(status='pending').count()
    from ..models import CustomerOTP
    pending_resets = []
    by_phone = {r.phone: r for r in riders}
    for otp in CustomerOTP.objects.filter(purpose='rider_reset', is_used=False,
                                          expires_at__gt=now()).order_by('-created_at')[:20]:
        rider = by_phone.get(otp.phone)
        if rider and not otp.is_sent_to_customer:      # automatic nahi gaya -> manager ko bataana hai
            pending_resets.append({'rider': rider, 'code': otp.otp_code, 'expires_at': otp.expires_at})
    return render(request, 'customer_portal/rider/manage.html', {
        'pending_resets': pending_resets,
        'riders': riders,
        'total_cash': sum((r.bal['cash_in_hand'] for r in riders), Decimal('0')),
        'total_due': sum((r.bal['due'] for r in riders), Decimal('0')),
    })


@_admin_only
def rider_detail(request, pk):
    rider = get_object_or_404(RiderProfile, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'fee':
            fee = _money(request.POST.get('fee'))
            if fee is None:
                messages.error(request, '❌ Fee is not valid.')
            else:
                rider.per_delivery_fee = fee
                rider.save(update_fields=['per_delivery_fee'])
                messages.success(request, f'✅ Fee set to Rs. {fee:,.0f} per delivery (applies to new orders).')
        elif action in ('cash_in', 'payout'):
            amount = _money(request.POST.get('amount'))
            bal = rider_balances(rider)
            limit = bal['cash_in_hand'] if action == 'cash_in' else bal['due']
            if not amount or amount <= 0:
                messages.error(request, '❌ Enter a valid amount.')
            elif amount > limit:
                messages.error(request, f'❌ Amount is too high. Maximum is Rs. {limit:,.0f}.')
            else:
                RiderSettlement.objects.create(rider=rider, kind=action, amount=amount,
                                               note=request.POST.get('note', '').strip()[:200],
                                               created_by=request.user)
                messages.success(request, f'✅ {"Cash jama" if action == "cash_in" else "Kamai ada"}: Rs. {amount:,.0f} ({rider.name})')
        return redirect('rider_detail', pk=rider.pk)

    deliveries = (rider.deliveries.filter(status='delivered', sale_order__isnull=False)
                  .select_related('sale_order').order_by('-delivered_at')[:30])
    return render(request, 'customer_portal/rider/detail.html', {
        'r': rider, 'b': rider_balances(rider), 'deliveries': deliveries,
        'rating': rider_rating(rider),
        'reviews': rider.reviews.filter(rider_rating__isnull=False).select_related('sale_order')[:10],
        'settlements': rider.settlements.select_related('created_by')[:30],
    })

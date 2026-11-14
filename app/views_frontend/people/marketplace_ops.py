"""Frontend views: Marketplace Operations dashboard (Talabat jaisa live control room).

Ek page par: aaj ke KPIs, live orders (stage-wise + late alerts), riders ki halat, live map,
top vendors, hourly orders, aur kaam talab cheezein (pending approvals, open disputes).
Page har ~20 second mein JSON endpoint se khud refresh hota hai.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from ...models import (CompanyInfo, DeliveryInfo, OrderDispute, OrderReview, Product, RiderProfile,
                       SaleOrder, SaleOrderItem, VendorProfile)
from ...security.permissions import perm_required
from ...utils import marketplace_ops_rules as rules

PERIODS = [(1, 'Aaj'), (7, 'Pichhle 7 din'), (30, 'Pichhle 30 din')]
ACTIVE_ORDER_STATUSES = ('pending', 'confirmed', 'processing', 'ready')
DONE_STATUSES = ('delivered', 'invoiced')
RIDER_ACTIVE_STATUSES = ('assigned', 'picked_up', 'in_transit')
LIVE_LIST_LIMIT = 60


def _mo_f(x):
    return float(x or 0)


def _period_start(days):
    """days=1 -> aaj raat 12 baje se; baaqi -> itne din pehle."""
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=max(days, 1) - 1)


def _delivery(order):
    try:
        return order.delivery_info
    except DeliveryInfo.DoesNotExist:
        return None


def _commission_pct(profile):
    from ...customer.vendor_commission import commission_percent
    try:
        return float(commission_percent(profile))
    except Exception:           # kharab data se dashboard na tootay
        return 0.0


def build_riders(now=None):
    """Online riders ki halat (offline chhupe hue). Wapas: (riders list, state ginti dict).
    Dispatch board bhi yahi use karta hai."""
    now = now or timezone.now()
    riders, state_counts = [], {'idle': 0, 'busy': 0, 'stale': 0, 'offline': 0}
    open_by_rider = {r['rider_id']: r['n'] for r in
                     DeliveryInfo.objects.filter(rider__isnull=False, status__in=RIDER_ACTIVE_STATUSES)
                     .order_by().values('rider_id').annotate(n=Count('id'))}
    for r in RiderProfile.objects.filter(is_active=True, approval_status='approved'):
        age_sec = (now - r.last_seen_at).total_seconds() if r.last_seen_at else None
        state = rules.rider_state(r.is_active, r.is_online, age_sec, open_by_rider.get(r.pk, 0))
        state_counts[state] += 1
        if state == 'offline':
            continue
        riders.append({
            'id': r.pk, 'name': r.name, 'phone': r.phone, 'vehicle': r.vehicle, 'state': state,
            'open': open_by_rider.get(r.pk, 0),
            'lat': _mo_f(r.last_lat) if r.last_lat is not None else None,
            'lng': _mo_f(r.last_lng) if r.last_lng is not None else None,
            'seen_txt': rules.fmt_minutes(age_sec / 60.0) if age_sec is not None else '-',
        })
    riders.sort(key=lambda r: ({'busy': 0, 'idle': 1, 'stale': 2}.get(r['state'], 3), r['name']))
    return riders, state_counts


def build_snapshot(days=1):
    """Dashboard ka sara data ek dict mein (JSON-safe). Page aur JSON endpoint dono yahi use karte hain."""
    now = timezone.now()
    start = _period_start(days)
    period_orders = SaleOrder.objects.filter(vendor__isnull=False, created_at__gte=start)

    # ---------------- KPIs ----------------
    counts = period_orders.aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(status__in=DONE_STATUSES)),
        cancelled=Count('id', filter=Q(status='cancelled')),
        active=Count('id', filter=Q(status__in=ACTIVE_ORDER_STATUSES)),
    )
    done_items = SaleOrderItem.objects.filter(order__in=period_orders.filter(status__in=DONE_STATUSES))
    sales_by_vendor = {r['order__vendor_id']: _mo_f(r['t']) for r in
                       done_items.order_by().values('order__vendor_id').annotate(t=Sum('total_amt'))}
    items_total = sum(sales_by_vendor.values())
    delivery_fees = _mo_f(period_orders.filter(status__in=DONE_STATUSES).aggregate(t=Sum('delivery_fee'))['t'])
    discounts = _mo_f(period_orders.filter(status__in=DONE_STATUSES).aggregate(t=Sum('discount_value'))['t'])

    profiles = {p.vendor_id: p for p in VendorProfile.objects.select_related('vendor')}
    commission = 0.0
    for vid, sales in sales_by_vendor.items():
        p = profiles.get(vid)
        if p:
            commission += rules.commission_amount(sales, _commission_pct(p))

    done_deliveries = DeliveryInfo.objects.filter(
        sale_order__in=period_orders.filter(status__in=DONE_STATUSES), delivered_at__isnull=False
    ).select_related('sale_order')
    mins = [rules.minutes_between(d.sale_order.created_at, d.delivered_at) for d in done_deliveries]
    mins = [m for m in mins if m is not None]
    avg_delivery = sum(mins) / len(mins) if mins else None

    ratings = OrderReview.objects.filter(created_at__gte=start, vendor_rating__isnull=False) \
        .aggregate(avg=Avg('vendor_rating'), n=Count('id'))
    avg_rating = round(_mo_f(ratings['avg']), 1) if ratings['n'] else None

    kpis = {
        'orders': counts['total'], 'delivered': counts['delivered'], 'cancelled': counts['cancelled'],
        'active': counts['active'],
        'cancel_rate': rules.percent(counts['cancelled'], counts['total']),
        'gmv': round(items_total + delivery_fees - discounts, 2),
        'items_total': round(items_total, 2), 'delivery_fees': round(delivery_fees, 2),
        'commission': round(commission, 2),
        'avg_order_value': round((items_total + delivery_fees - discounts) / counts['delivered'], 2)
        if counts['delivered'] else None,
        'avg_delivery_txt': rules.fmt_minutes(avg_delivery),
        'avg_rating': avg_rating, 'rating_n': ratings['n'],
    }

    # ---------------- Live orders ----------------
    live_qs = SaleOrder.objects.filter(vendor__isnull=False, status__in=ACTIVE_ORDER_STATUSES) \
        .select_related('customer', 'vendor', 'delivery_info', 'delivery_info__rider') \
        .order_by('created_at')
    live, stage_counts, late_total, unassigned_total = [], {s: 0 for s in rules.STAGES}, 0, 0
    drop_points, active_vendor_ids = [], set()
    for o in live_qs[:300]:
        # Scheduled order jo abhi door hai, late/active nahi ginte
        if o.scheduled_for and o.scheduled_for > now + timedelta(minutes=45):
            continue
        d = _delivery(o)
        stage = rules.order_stage(o.status, d.status if d else None)
        if stage is None:
            continue
        age = rules.minutes_between(o.created_at, now)
        since_ready = rules.minutes_between(o.updated_at, now) if stage == rules.STAGE_READY else None
        since_pickup = rules.minutes_between(d.picked_up_at, now) if (d and d.picked_up_at) else None
        has_rider = bool(d and d.rider_id)
        late = rules.order_late_reason(stage, age, o.prep_minutes, has_rider, since_ready, since_pickup)
        stage_counts[stage] += 1
        active_vendor_ids.add(o.vendor_id)
        needs_rider = stage == rules.STAGE_READY and not has_rider
        if late:
            late_total += 1
        if needs_rider:
            unassigned_total += 1
            if o.delivery_lat is not None and o.delivery_lng is not None:
                drop_points.append({'lat': _mo_f(o.delivery_lat), 'lng': _mo_f(o.delivery_lng), 'order_no': o.order_no})
        live.append({
            'id': o.pk, 'order_no': o.order_no, 'stage': stage, 'status': o.status,
            'vendor': o.vendor.name, 'customer': o.customer.name,
            'age_min': int(age or 0), 'age_txt': rules.fmt_minutes(age),
            'rider': (d.rider.name if d and d.rider_id else ''), 'needs_rider': needs_rider,
            'late': late or '', 'scheduled': bool(o.scheduled_for),
            'url': reverse('order_tracking_detail', args=[o.pk]),
        })
    # Late pehle, phir sab se purana
    live.sort(key=lambda r: (not r['late'], -r['age_min']))
    live_total = len(live)
    live = live[:LIVE_LIST_LIMIT]

    # ---------------- Riders ----------------
    riders, state_counts = build_riders(now)

    # ---------------- Vendors ----------------
    vendor_rows = []
    by_vendor = {r['vendor_id']: r for r in period_orders.order_by().values('vendor_id').annotate(
        n=Count('id'), c=Count('id', filter=Q(status='cancelled')))}
    for vid, b in by_vendor.items():
        p = profiles.get(vid)
        if not p:
            continue
        sales = sales_by_vendor.get(vid, 0.0)
        vendor_rows.append({
            'name': p.business_name, 'orders': b['n'], 'cancelled': b['c'],
            'cancel_rate': rules.percent(b['c'], b['n']), 'sales': round(sales, 2),
            'commission': rules.commission_amount(sales, _commission_pct(p)),
        })
    vendor_rows.sort(key=lambda r: (-r['sales'], -r['orders']))
    store_pins = [{'name': p.business_name, 'lat': _mo_f(p.lat), 'lng': _mo_f(p.lng)}
                  for p in profiles.values()
                  if p.lat is not None and p.lng is not None and p.vendor_id in active_vendor_ids]

    # ---------------- Hourly (aaj ya period ki ginti) ----------------
    hours = [timezone.localtime(dt).hour for dt in
             period_orders.values_list('created_at', flat=True)]
    hourly = rules.hourly_buckets(hours)

    # ---------------- Action items ----------------
    todo = {
        'pending_accounts': VendorProfile.objects.filter(is_approved=False, approved_at__isnull=True).count(),
        'pending_products': Product.objects.filter(vendor__isnull=False, approval_status='pending').count(),
        'open_disputes': OrderDispute.objects.filter(status__in=OrderDispute.OPEN_STATUSES).count(),
        'pending_riders': RiderProfile.objects.filter(approval_status='pending').count(),
    }

    return {
        'generated_at': timezone.localtime(now).strftime('%H:%M:%S'),
        'days': days, 'currency': getattr(settings, 'CURRENCY_LABEL', 'Rs.'),
        'kpis': kpis, 'stage_counts': stage_counts, 'live_total': live_total,
        'late_total': late_total, 'unassigned_total': unassigned_total,
        'live': live, 'riders': riders, 'rider_counts': state_counts,
        'vendors': vendor_rows[:10], 'hourly': hourly, 'todo': todo,
        'map': {'riders': [r for r in riders if r['lat'] is not None],
                'stores': store_pins, 'drops': drop_points[:50]},
    }


def _days_param(request):
    try:
        days = int(request.GET.get('days', 1))
    except ValueError:
        days = 1
    return days if days in dict(PERIODS) else 1


@login_required
@perm_required('view_vendors')
def marketplace_ops(request):
    days = _days_param(request)
    return render(request, 'oversight/marketplace_ops.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'snapshot': build_snapshot(days), 'days': days, 'periods': PERIODS,
        'data_url': reverse('marketplace_ops_data'),
    })


@login_required
@perm_required('view_vendors')
def marketplace_ops_data(request):
    resp = JsonResponse(build_snapshot(_days_param(request)))
    resp['Cache-Control'] = 'no-store'
    return resp

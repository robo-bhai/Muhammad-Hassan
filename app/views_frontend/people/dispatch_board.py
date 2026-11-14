"""Frontend views: Live Dispatch Board (admin ke liye rider assign karne ka control room).

Teen column: 'Rider chahiye' (ready, rider nahi), 'Rider mil gaya' (uthane ka intezar),
'Tayyar ho raha hai' (sirf dekhne ke liye). Har ready order par nazdeek ke riders suggest hote hain
(fasla + load, auto-dispatch jaisi tarteeb) aur ek click se assign ho jata hai.
"""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ...models import CompanyInfo, DeliveryInfo, RiderProfile, SaleOrder
from ...security.permissions import perm_required
from ...utils import dispatch_board_rules as dr
from ...utils.marketplace_ops_rules import fmt_minutes, minutes_between

BOARD_STATUSES = ('confirmed', 'processing', 'ready')
BOARD_LIMIT = 150


def _db_num(x):
    return float(x) if x is not None else None


def _db_attr(obj, name):
    """Reverse one-to-one jo maujood na ho to None (RelatedObjectDoesNotExist ke bajaye)."""
    try:
        return getattr(obj, name)
    except Exception:
        return None


def build_board():
    """Board ka sara data (JSON-safe dict)."""
    from .marketplace_ops import build_riders
    now = timezone.now()
    riders, rider_counts = build_riders(now)
    rider_names = {r['id']: r['name'] for r in riders}

    qs = (SaleOrder.objects.filter(vendor__isnull=False, status__in=BOARD_STATUSES)
          .select_related('customer', 'vendor', 'vendor__portal_profile', 'delivery_info',
                          'delivery_info__rider', 'dispatch_attempt')
          .annotate(n_items=Count('items'))
          .order_by('created_at'))
    cols = {dr.COL_NEEDS: [], dr.COL_ASSIGNED: [], dr.COL_PREPARING: []}
    store_ids = set()
    for o in qs[:BOARD_LIMIT]:
        if o.scheduled_for and o.scheduled_for > now + timedelta(minutes=45):
            continue                      # door ka scheduled order abhi board par nahi
        d = _db_attr(o, 'delivery_info')
        col = dr.board_column(o.status, d.status if d else None, bool(d and d.rider_id))
        if col is None:
            continue
        prof = _db_attr(o.vendor, 'portal_profile')
        s_lat, s_lng = _db_num(getattr(prof, 'lat', None)), _db_num(getattr(prof, 'lng', None))
        age = minutes_between(o.created_at, now)
        card = {
            'id': o.pk, 'order_no': o.order_no, 'column': col, 'status': o.status,
            'vendor': o.vendor.name, 'customer': o.customer.name, 'items': o.n_items,
            'age_min': int(age or 0), 'age_txt': fmt_minutes(age),
            'store': {'lat': s_lat, 'lng': s_lng},
            'drop': {'lat': _db_num(o.delivery_lat), 'lng': _db_num(o.delivery_lng)},
            'payment': o.payment_method or '', 'url': reverse('order_tracking_detail', args=[o.pk]),
            'rider': None, 'suggestions': [], 'offer': None,
        }
        if col == dr.COL_PREPARING:
            left = (o.prep_minutes - age) if (o.prep_minutes and age is not None) else None
            card['prep_left_txt'] = ('~' + fmt_minutes(left) + ' left') if (left is not None and left > 0) \
                else ('due now' if left is not None else '')
        else:
            ready_for = minutes_between(o.updated_at, now)
            card['ready_txt'] = fmt_minutes(ready_for)
            card['waiting_min'] = int(ready_for or 0)
            if d and d.rider_id:
                card['rider'] = {'id': d.rider_id, 'name': d.rider.name, 'phone': d.rider.phone}
            card['suggestions'] = [
                {k: x[k] for k in ('id', 'name', 'state', 'open', 'dist_km', 'eta_min', 'full')}
                for x in dr.suggest_riders(s_lat, s_lng, riders)
                if not (d and d.rider_id == x['id'])]
            att = _db_attr(o, 'dispatch_attempt')
            if att and col == dr.COL_NEEDS and att.ranking:
                card['offer'] = {
                    'started_min': int(minutes_between(att.started_at, now) or 0),
                    'ranking': [{'id': i, 'name': rider_names.get(i, f'#{i}'), 'declined': i in att.declined}
                                for i in att.ranking]}
        if s_lat is not None:
            store_ids.add(o.vendor_id)
        cols[col].append(card)

    # Rider chahiye wale pehle sab se zyada intezar karne wale
    cols[dr.COL_NEEDS].sort(key=lambda c: -c['waiting_min'])
    return {
        'generated_at': timezone.localtime(now).strftime('%H:%M:%S'),
        'columns': cols,
        'counts': {k: len(v) for k, v in cols.items()},
        'riders': riders, 'rider_counts': rider_counts,
        'max_active': dr.MAX_ACTIVE_ORDERS,
    }


@login_required
@perm_required('view_vendors')
def dispatch_board(request):
    return render(request, 'oversight/dispatch_board.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'snapshot': build_board(),
        'data_url': reverse('dispatch_board_data'),
        'assign_url': reverse('dispatch_board_assign'),
        'can_assign': request.user.is_superuser or _db_can(request.user, 'manage_orders'),
    })


def _db_can(user, key):
    from ...security.permissions import has_matrix_perm
    return has_matrix_perm(user, key)


@login_required
@perm_required('view_vendors')
def dispatch_board_data(request):
    resp = JsonResponse(build_board())
    resp['Cache-Control'] = 'no-store'
    return resp


@login_required
@perm_required('view_vendors', post='manage_orders')
@require_POST
def dispatch_board_assign(request):
    """Admin ready order par rider chunta hai. JSON wapas. force=1 -> chetawani (offline/full) nazar-andaz."""
    from ...customer import store_orders, views_rider_portal as vrp

    try:
        order_id = int(request.POST.get('order_id') or 0)
        rider_id = int(request.POST.get('rider_id') or 0)
    except ValueError:
        return JsonResponse({'ok': False, 'message': 'Bad request.'}, status=400)
    force = request.POST.get('force') == '1'

    rider = RiderProfile.objects.select_related('user').filter(
        pk=rider_id, is_active=True, approval_status='approved').first()
    if not rider:
        return JsonResponse({'ok': False, 'message': 'Rider not found or not approved.'}, status=404)

    with transaction.atomic():
        order = SaleOrder.objects.select_for_update().filter(pk=order_id, vendor__isnull=False).first()
        if not order:
            return JsonResponse({'ok': False, 'message': 'Order not found.'}, status=404)
        di, _ = DeliveryInfo.objects.select_for_update().get_or_create(sale_order=order)
        ok, why = dr.can_assign(order.status, di.status)
        if not ok:
            return JsonResponse({'ok': False, 'message': why}, status=409)
        if di.rider_id == rider.pk:
            return JsonResponse({'ok': False, 'message': f'{rider.name} is already assigned.'}, status=409)

        warnings = []
        now = timezone.now()
        fresh = rider.last_seen_at and (now - rider.last_seen_at).total_seconds() <= 120
        if not (rider.is_online and fresh):
            warnings.append(f'{rider.name} looks offline / has no signal.')
        open_n = DeliveryInfo.objects.filter(rider=rider, status__in=vrp.ACTIVE_STATUSES) \
            .exclude(sale_order=order).count()
        if open_n >= dr.MAX_ACTIVE_ORDERS:
            warnings.append(f'{rider.name} already has {open_n} active orders.')
        if warnings and not force:
            return JsonResponse({'ok': False, 'needs_confirm': True, 'message': ' '.join(warnings)}, status=409)

        old_rider = di.rider if di.rider_id else None
        vrp._assign(order, di, rider, request.user)
        store_orders._notify(rider.user, f'🏍️ Naya order #{order.order_no}',
                             f'{store_orders.store_name(order.vendor_id)} se maal uthana hai.',
                             reverse('rider_home'), 'info')
        if old_rider and old_rider.user_id:
            store_orders._notify(old_rider.user, f'Order #{order.order_no} ab aap ke paas nahi',
                                 'Admin ne ye order kisi aur rider ko de diya.', reverse('rider_home'), 'info')
    return JsonResponse({'ok': True, 'message': f'Order #{order.order_no} → {rider.name}'})

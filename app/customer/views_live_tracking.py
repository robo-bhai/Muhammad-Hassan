"""
Live rider tracking (Talabat jaisa map).

  POST shop/rider/api/location/        -> rider ka phone apni location bhejta hai
  GET  shop/track/live/<order_id>/     -> customer (login) apne order ke rider ki location lata hai
  GET  shop/track/live-public/?t=...   -> public tracking page (order no + phone ke baad mila signed token)
  POST shop/api/drop-location/         -> customer apni delivery location ka pin lagata hai

Privacy: location sirf tab milti hai jab delivery chal rahi ho (assigned / picked_up / in_transit).
"""
import math
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from ..models import DeliveryInfo, RiderProfile, SaleOrder
from . import drop_pin, location_sync
from .views_rider_portal import ACTIVE_STATUSES, rider_login_required

MIN_SECONDS_BETWEEN_UPDATES = 3
STALE_AFTER_SECONDS = 90
LIVE_TOKEN_SALT = 'live-track'
LIVE_TOKEN_MAX_AGE = 2 * 3600


def parse_coords(lat, lng):
    """(lat, lng) -> (Decimal, Decimal) ya None agar ghalat ho."""
    try:
        la, lo = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(la) and math.isfinite(lo)):
        return None
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        return None
    if la == 0 and lo == 0:
        return None
    return Decimal(str(round(la, 7))), Decimal(str(round(lo, 7)))


@rider_login_required
@require_POST
def rider_location_update(request):
    rider = request.user.rider_profile
    coords = parse_coords(request.POST.get('lat'), request.POST.get('lng'))
    if coords is None:
        return JsonResponse({'ok': False, 'error': 'bad_coords'}, status=400)
    if not rider.is_online:
        return JsonResponse({'ok': False, 'error': 'offline'}, status=409)
    now = timezone.now()
    # Offline queue se aayi point mein `at` (epoch seconds) hota hai: purani point naye ko overwrite nahi karti.
    captured, reason = location_sync.resolve_capture(
        request.POST.get('at'), now.timestamp(),
        rider.last_location_at.timestamp() if rider.last_location_at else None,
        min_gap=MIN_SECONDS_BETWEEN_UPDATES)
    if captured is None:
        return JsonResponse({'ok': True, 'skipped': True, 'reason': reason})
    RiderProfile.objects.filter(pk=rider.pk).update(
        last_lat=coords[0], last_lng=coords[1],
        last_location_at=datetime.fromtimestamp(captured, tz=dt_timezone.utc), last_seen_at=now)
    return JsonResponse({'ok': True})


def make_live_token(order):
    """Public tracking page ke liye signed token (order no + phone sahi hone ke baad hi banta hai)."""
    return signing.dumps({'o': order.id}, salt=LIVE_TOKEN_SALT)


def _live_payload(order):
    di = (DeliveryInfo.objects.filter(sale_order=order, status__in=ACTIVE_STATUSES)
          .select_related('rider').first())
    rider = di.rider if di else None
    if rider is None or rider.last_lat is None or rider.last_lng is None:
        return {'active': False}
    age = (timezone.now() - rider.last_location_at).total_seconds() if rider.last_location_at else None
    data = {
        'active': True,
        'lat': float(rider.last_lat),
        'lng': float(rider.last_lng),
        'age': int(age) if age is not None else None,
        'stale': age is None or age > STALE_AFTER_SECONDS,
        'status': di.status,
        'rider_name': rider.name,
    }
    if order.delivery_lat is not None and order.delivery_lng is not None:
        data['dest_lat'] = float(order.delivery_lat)
        data['dest_lng'] = float(order.delivery_lng)
    return data


@login_required
@require_GET
def customer_rider_location(request, order_id):
    profile = getattr(request.user, 'customer_profile', None)
    if profile is None:
        return JsonResponse({'active': False}, status=403)
    order = SaleOrder.objects.filter(id=order_id, customer=profile.customer).first()
    if order is None:
        return JsonResponse({'active': False}, status=404)
    return JsonResponse(_live_payload(order))


@require_GET
def track_live_public(request):
    try:
        data = signing.loads(request.GET.get('t', ''), salt=LIVE_TOKEN_SALT, max_age=LIVE_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return JsonResponse({'active': False}, status=403)
    order = SaleOrder.objects.filter(id=data.get('o')).first()
    if order is None:
        return JsonResponse({'active': False}, status=404)
    return JsonResponse(_live_payload(order))


@login_required
@require_POST
def customer_set_drop_location(request):
    if getattr(request.user, 'customer_profile', None) is None:
        return JsonResponse({'ok': False}, status=403)
    coords = parse_coords(request.POST.get('lat'), request.POST.get('lng'))
    if coords is None:
        return JsonResponse({'ok': False, 'error': 'bad_coords'}, status=400)
    drop_pin.save_pin(request.session, coords[0], coords[1])
    return JsonResponse({'ok': True})

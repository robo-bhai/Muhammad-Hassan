"""Store ki delivery fee: fixed fee + (customer ke pin ki doori ke hisab se per-km) + (area ka extra charge).

Sab kuch admin switch `shop_distance_fee_enabled` ke peeche hai. Switch OFF, ya store ne fee_per_km /
max_delivery_km set na kiya ho, ya customer ka pin na ho -> purani fixed fee jyon ki tyon chalti hai.
"""
from decimal import Decimal, ROUND_HALF_UP
from math import asin, cos, radians, sin, sqrt

ZERO = Decimal('0')


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = (float(x) for x in (lat1, lng1, lat2, lng2))
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def compute_fee(base_fee, fee_per_km, free_radius_km, distance_km, area_extra=ZERO):
    """Pure hisab. distance_km None ho to sirf base (+ area extra). Fee poore rupay tak round."""
    base = Decimal(base_fee or 0)
    extra_area = Decimal(area_extra or 0)
    per_km = Decimal(fee_per_km or 0)
    dist_part = ZERO
    if distance_km is not None and per_km > 0:
        over = max(Decimal(str(distance_km)) - Decimal(free_radius_km or 0), ZERO)
        dist_part = per_km * over
    return (base + dist_part + extra_area).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _area_extra(request):
    """Customer ke chune hue area ka extra charge (DeliveryArea.extra_fee). (extra, label)"""
    from ..models import DeliveryArea
    try:
        from .views_customer_portal import get_delivery_area
        area = (get_delivery_area(request) or '').strip().lower()
    except Exception:
        return ZERO, ''
    if not area:
        return ZERO, ''
    for a in DeliveryArea.objects.filter(is_active=True, extra_fee__gt=0):
        label = a.label.lower()
        if area == label or area == a.name.lower() or a.name.lower() in area:
            return Decimal(a.extra_fee), a.name
    return ZERO, ''


def quote(prof, request=None, area_pre=None):
    """Store `prof` ke liye abhi ki delivery fee.
    area_pre = (extra, naam) pehle se nikala hua ho (list page par har store ke liye dobara query na ho).
    Lautata hai: {'fee', 'distance_km', 'area_extra', 'area_name', 'out_of_range', 'message', 'dynamic'}"""
    base = Decimal(prof.delivery_fee or 0)
    out = {'fee': base, 'distance_km': None, 'area_extra': ZERO, 'area_name': '',
           'out_of_range': False, 'message': '', 'dynamic': False}
    from ..module_config.shop_flags import shop_flag
    if not shop_flag('shop_distance_fee_enabled'):
        return out
    if request is None:
        from ..middleware.request_context import current_request
        request = current_request()
    if request is None:
        return out

    per_km = Decimal(prof.fee_per_km or 0)
    max_km = prof.max_delivery_km
    distance = None
    if prof.lat is not None and prof.lng is not None and (per_km > 0 or max_km):
        from . import drop_pin
        pin = drop_pin.read_pin(request.session)
        if pin:
            distance = round(haversine_km(prof.lat, prof.lng, pin[0], pin[1]), 1)
            out['distance_km'] = distance

    if distance is not None and max_km and Decimal(str(distance)) > Decimal(max_km):
        out['out_of_range'] = True
        out['message'] = (f'{prof.business_name} sirf {max_km} km tak deliver karta hai '
                          f'(aap {distance} km door hain).')

    extra, area_name = area_pre if area_pre is not None else _area_extra(request)
    out['area_extra'], out['area_name'] = extra, area_name
    out['fee'] = compute_fee(base, per_km, prof.free_radius_km, distance, extra)
    out['dynamic'] = distance is not None or extra > 0
    return out

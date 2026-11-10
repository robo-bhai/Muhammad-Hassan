"""
Auto rider dispatch (nazdeek rider ko pehle offer).

Kaise chalta hai (koi background worker nahi chahiye):
  1. Order 'ready' hone ke baad jab pehli dafa koi rider page/poll karta hai, ek DispatchAttempt
     banta hai: eligible riders (online, taaza, capacity bachi) fasle + load ke hisaab se rank hote hain.
  2. Rank 0 rider ko order foran dikhta hai, rank 1 ko WINDOW_SECONDS baad, rank 2 ko 2*WINDOW baad...
  3. OPEN_AFTER_SECONDS ke baad (ya jab saare ranked riders reject kar den) order sab riders ko dikhta hai
     (purana "jo pehle accept kare" system).
Rider ko accept to khud karna hota hai (COD cash ka masla hai), bas offer ki tarteeb auto hai.
"""
import math
from datetime import timedelta

WINDOW_SECONDS = 20          # har agle rider ko itne second baad offer
OPEN_AFTER_SECONDS = 90      # is ke baad sab ko dikhe
MAX_RANKED = 5
SEEN_FRESH_SECONDS = 120     # rider itne second mein active hona chahiye
LOCATION_FRESH_SECONDS = 180
LOAD_PENALTY_KM = 1.0        # har active order = itne km door ke barabar


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def rank_candidates(candidates, store_lat, store_lng, limit=MAX_RANKED):
    """candidates: [{'id','lat','lng','active'}]  ->  rider ids, sab se munasib pehle."""
    def key(c):
        located = (store_lat is not None and store_lng is not None
                   and c.get('lat') is not None and c.get('lng') is not None)
        if located:
            score = haversine_km(store_lat, store_lng, c['lat'], c['lng']) + c['active'] * LOAD_PENALTY_KM
            return (0, score, c['id'])
        return (1, c['active'], c['id'])
    return [c['id'] for c in sorted(candidates, key=key)[:limit]]


def is_visible(rider_id, ranking, declined, elapsed, window=WINDOW_SECONDS, open_after=OPEN_AFTER_SECONDS):
    """Kya ye rider is order ka offer abhi dekh sakta hai?"""
    if rider_id in declined:
        return False
    if not ranking:
        return True
    if all(r in declined for r in ranking):
        return True
    if elapsed >= open_after:
        return True
    if rider_id in ranking:
        return elapsed >= ranking.index(rider_id) * window
    return False


# ---------------- DB wala hissa ----------------

def _store_coords(order):
    prof = getattr(order.vendor, 'portal_profile', None) if order.vendor_id else None
    lat, lng = getattr(prof, 'lat', None), getattr(prof, 'lng', None)
    if lat is None or lng is None:
        return None, None
    return float(lat), float(lng)


def _rider_coords(rider, now):
    if rider.last_lat is None or rider.last_lng is None or not rider.last_location_at:
        return None, None
    if (now - rider.last_location_at).total_seconds() > LOCATION_FRESH_SECONDS:
        return None, None
    return float(rider.last_lat), float(rider.last_lng)


def distance_km(order, rider):
    """Store se rider ka fasla (1 decimal) ya None."""
    from django.utils import timezone
    s_lat, s_lng = _store_coords(order)
    r_lat, r_lng = _rider_coords(rider, timezone.now())
    if None in (s_lat, s_lng, r_lat, r_lng):
        return None
    return round(haversine_km(s_lat, s_lng, r_lat, r_lng), 1)


def _compute_ranking(order, max_active, active_statuses):
    from django.db.models import Count, Q
    from django.utils import timezone
    from ..models import RiderProfile
    now = timezone.now()
    riders = (RiderProfile.objects
              .filter(is_active=True, is_online=True,
                      last_seen_at__gte=now - timedelta(seconds=SEEN_FRESH_SECONDS))
              .annotate(active_n=Count('deliveries', filter=Q(deliveries__status__in=active_statuses))))
    cands = []
    for r in riders:
        if r.active_n >= max_active:
            continue
        lat, lng = _rider_coords(r, now)
        cands.append({'id': r.id, 'lat': lat, 'lng': lng, 'active': r.active_n})
    s_lat, s_lng = _store_coords(order)
    return rank_candidates(cands, s_lat, s_lng)


def get_attempt(order, max_active, active_statuses):
    from ..models import DispatchAttempt
    att = DispatchAttempt.objects.filter(sale_order=order).first()
    if att:
        return att
    ranking = _compute_ranking(order, max_active, active_statuses)
    att, _ = DispatchAttempt.objects.get_or_create(sale_order=order, defaults={'ranking': ranking})
    return att


def can_take(order, rider, max_active, active_statuses):
    from django.utils import timezone
    att = get_attempt(order, max_active, active_statuses)
    elapsed = (timezone.now() - att.started_at).total_seconds()
    return is_visible(rider.id, att.ranking, att.declined, elapsed)


def visible_orders(orders, rider, max_active, active_statuses):
    return [o for o in orders if can_take(o, rider, max_active, active_statuses)]


def decline(order, rider):
    from django.db import transaction
    from ..models import DispatchAttempt
    with transaction.atomic():
        att = DispatchAttempt.objects.select_for_update().filter(sale_order=order).first()
        if att and rider.id not in att.declined:
            att.declined = list(att.declined) + [rider.id]
            att.save(update_fields=['declined'])

"""Live dispatch board ke pure rules (Django ka koi import nahi - seedha test ho sakte hain).

Scoring app/customer/dispatch.py jaisi hai (fasla + har active order = LOAD_PENALTY_KM), taake
board ki 'suggested' tarteeb aur auto-dispatch ki tarteeb mel khayen.
"""
import math

MAX_ACTIVE_ORDERS = 3        # views_rider_portal.MAX_ACTIVE_ORDERS ke barabar
LOAD_PENALTY_KM = 1.0        # dispatch.LOAD_PENALTY_KM ke barabar
AVG_SPEED_KMH = 20.0         # shehar mein bike ki andaazi raftaar (sirf ETA ke liye)
MAX_SUGGESTIONS = 5

# Order cards ke columns
COL_NEEDS = 'needs_rider'    # ready, rider nahi
COL_ASSIGNED = 'assigned'    # rider mil gaya, abhi uthaya nahi
COL_PREPARING = 'preparing'  # store tayyar kar raha hai (sirf dekhne ke liye)


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def eta_minutes(km):
    """Fasle se andaazi minute (kam az kam 1) ya None."""
    if km is None:
        return None
    return max(1, int(round(km / AVG_SPEED_KMH * 60)))


def board_column(status, delivery_status, has_rider):
    """Order board par kis column mein jata hai (None = board par nahi)."""
    if status in ('confirmed', 'processing'):
        return COL_PREPARING
    if status != 'ready':
        return None
    if delivery_status in ('picked_up', 'in_transit', 'delivered', 'cancelled'):
        return None
    return COL_ASSIGNED if has_rider else COL_NEEDS


def can_assign(order_status, delivery_status):
    """(ok, wajah). Sirf 'ready' order jise rider ne abhi uthaya nahi."""
    if order_status != 'ready':
        return False, 'Rider sirf "Ready" order par chun sakte hain.'
    if delivery_status in ('picked_up', 'in_transit', 'delivered'):
        return False, 'Rider order utha chuka hai, ab badla nahi ja sakta.'
    return True, ''


def suggest_riders(store_lat, store_lng, riders, max_active=MAX_ACTIVE_ORDERS, limit=MAX_SUGGESTIONS):
    """riders: [{'id','state','open','lat','lng', ...}] -> munasib riders, behtareen pehle.

    Sirf 'idle' aur 'busy' (online, taaza signal) riders. Capacity bhar chuke riders list mein rehte
    hain par 'full' flag ke saath aur sab se aakhir mein. Har dict mein dist_km, eta_min, full add hota hai."""
    out = []
    for r in riders:
        if r.get('state') not in ('idle', 'busy'):
            continue
        located = None not in (store_lat, store_lng, r.get('lat'), r.get('lng'))
        km = round(haversine_km(store_lat, store_lng, r['lat'], r['lng']), 1) if located else None
        open_n = r.get('open', 0)
        item = dict(r, dist_km=km, eta_min=eta_minutes(km), full=open_n >= max_active)
        item['_score'] = (km if located else 1e6) + open_n * LOAD_PENALTY_KM
        out.append(item)
    out.sort(key=lambda x: (x['full'], x['_score'], x['id']))
    for x in out:
        x.pop('_score', None)
    return out[:limit]

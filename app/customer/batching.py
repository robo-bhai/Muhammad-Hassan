"""Order batching: rider ke ek hi raaste ke 2-3 orders.

Do kaam (sab pure functions, DB ke bina):
1. match_offer  - naya offer rider ke maujooda orders ke saath "ek raaste" ka hai ya nahi.
2. plan_route   - rider ke active orders ka suggested sequence (pehle sab store se maal, phir
                  customers - sab se qareeb wala pehle) aur Google Maps multi-stop link.
Coordinates na hon to address se kaam chalta hai; kuch bhi na ho to koi badge/plan nahi banta.
"""
from urllib.parse import quote

from .dispatch import haversine_km

NEAR_STORE_KM = 1.5     # dono stores itne qareeb = saath uthaya ja sakta hai
NEAR_DROP_KM = 2.5      # dono customers itne qareeb = ek hi raaste par
MAX_WAYPOINTS = 8       # Google Maps URL ki hadd (9) se kam


def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _dist(a, b):
    """(lat, lng) ya None ke darmiyan km; coordinates na hon to None."""
    if not a or not b or None in a or None in b:
        return None
    return haversine_km(a[0], a[1], b[0], b[1])


def match_offer(offer, actives):
    """offer: {'vendor_id','store_ll','drop_ll'}; actives: isi shakal ki list.
    Return: 'same_store' | 'near_store' | 'same_area' | None (sab se majboot match pehle)."""
    if not actives:
        return None
    if offer.get('vendor_id') and any(a.get('vendor_id') == offer['vendor_id'] for a in actives):
        return 'same_store'
    for a in actives:
        d = _dist(offer.get('store_ll'), a.get('store_ll'))
        if d is not None and d <= NEAR_STORE_KM:
            return 'near_store'
    for a in actives:
        d = _dist(offer.get('drop_ll'), a.get('drop_ll'))
        if d is not None and d <= NEAR_DROP_KM:
            return 'same_area'
    return None


def _nearest_first(stops, start):
    """Nearest-neighbour tarteeb. Bina coordinates wale stops aakhir mein, apni asli tarteeb mein."""
    located = [s for s in stops if s['ll']]
    rest = [s for s in stops if not s['ll']]
    out, cur = [], start
    while located:
        if cur:
            nxt = min(located, key=lambda s: _dist(cur, s['ll']))
        else:
            nxt = located[0]
        located.remove(nxt)
        out.append(nxt)
        cur = nxt['ll']
    return out + rest


def plan_route(orders, start=None):
    """orders: [{'order_no','status','vendor_id','store_name','store_ll','store_addr',
                 'cust_name','drop_ll','cust_addr'}]
    status 'assigned' = maal abhi store se uthana hai. start = rider ki (lat, lng) ya None.
    Return {'stops': [...], 'google': url|'' } ; 2 se kam orders par None."""
    if len(orders) < 2:
        return None

    pickups, seen = [], {}
    for o in orders:
        if o['status'] != 'assigned':
            continue
        key = o.get('vendor_id') or ('addr', o.get('store_addr'))
        if key in seen:
            seen[key]['orders'].append(o['order_no'])
            continue
        s = {'kind': 'pickup', 'label': o.get('store_name') or 'Store', 'll': o.get('store_ll'),
             'addr': o.get('store_addr') or '', 'orders': [o['order_no']]}
        seen[key] = s
        pickups.append(s)
    pickups = _nearest_first(pickups, start)

    last = pickups[-1]['ll'] if pickups and pickups[-1]['ll'] else start
    drops = [{'kind': 'drop', 'label': o.get('cust_name') or 'Customer', 'll': o.get('drop_ll'),
              'addr': o.get('cust_addr') or '', 'orders': [o['order_no']]} for o in orders]
    drops = _nearest_first(drops, last)

    stops = [s for s in pickups + drops if s['ll'] or s['addr']]
    if len(stops) < 2:
        return None
    for i, s in enumerate(stops, 1):
        s['n'] = i
    return {'stops': stops, 'google': _google_url(stops)}


def _point(s):
    return f'{s["ll"][0]},{s["ll"][1]}' if s['ll'] else s['addr']


def _google_url(stops):
    """Pehla stop-ke-ilawa sab 'waypoints'; aakhri stop 'destination'. Bohat stops ho to pehle MAX_WAYPOINTS tak."""
    stops = stops[:MAX_WAYPOINTS + 1]
    dest = _point(stops[-1])
    way = '|'.join(_point(s) for s in stops[:-1])
    url = f'https://www.google.com/maps/dir/?api=1&destination={quote(dest)}&travelmode=two-wheeler'
    if way:
        url += f'&waypoints={quote(way)}'
    return url

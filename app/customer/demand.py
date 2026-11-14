"""Rider ke liye demand heat map aur shift planner (pure functions, DB ke bina).

rows: [(weekday 0=Mon, hour 0-23, vendor_id|None)] - pichle 28 din ke delivery orders.
stores: {vendor_id: {'name', 'lat', 'lng'}}.
Zone = store pickup location ke aas-paas ka ~1 km ka dabba. Customer ka koi data nahi dikhta.
"""
from collections import defaultdict

WINDOW_DAYS = 28
WEEKS = WINDOW_DAYS // 7          # har weekday window mein itni baar aata hai
GRID = 0.01                       # ~1.1 km
SHIFT_HOURS = 3
DAY_NAMES = ['Peer', 'Mangal', 'Budh', 'Jumeraat', 'Jumma', 'Hafta', 'Itwaar']


def hour_profile(rows, weekday=None):
    """24 hisson ki list: har ghante mein ausat orders. weekday=None = poore hafte ka ausat din."""
    counts = [0] * 24
    for wd, hr, _v in rows:
        if weekday is None or wd == weekday:
            counts[hr] += 1
    div = WEEKS if weekday is not None else WINDOW_DAYS
    return [round(c / div, 2) for c in counts]


def best_window(profile, length=SHIFT_HOURS):
    """Sab se zyada orders wali `length` ghante ki lagatar window: (start, end, avg_per_hour) ya None."""
    best = None
    for s in range(0, 24 - length + 1):
        total = sum(profile[s:s + length])
        if best is None or total > best[0]:
            best = (total, s)
    if best is None or best[0] <= 0:
        return None
    total, s = best
    return {'start': s, 'end': s + length, 'avg': round(total / length, 1)}


def weekly_plan(rows):
    """Har din ki behtareen shift - shift planner table."""
    out = []
    for wd in range(7):
        w = best_window(hour_profile(rows, wd))
        out.append({'weekday': wd, 'day': DAY_NAMES[wd], 'window': w})
    return out


def zones(rows, stores, hours=None, weekday=None, top=15):
    """Store-location ke dabbon mein order count. hours = sirf in ghanton ke orders (set), weekday = sirf us din."""
    cells = defaultdict(lambda: {'count': 0, 'names': defaultdict(int), 'lat': 0.0, 'lng': 0.0, 'n': 0})
    for wd, hr, vid in rows:
        if weekday is not None and wd != weekday:
            continue
        if hours is not None and hr not in hours:
            continue
        st = stores.get(vid)
        if not st or st.get('lat') is None or st.get('lng') is None:
            continue
        key = (round(st['lat'] / GRID), round(st['lng'] / GRID))
        c = cells[key]
        c['count'] += 1
        c['names'][st['name']] += 1
        c['lat'] += st['lat']
        c['lng'] += st['lng']
        c['n'] += 1
    out = []
    for c in cells.values():
        names = sorted(c['names'], key=lambda n: -c['names'][n])[:3]
        out.append({'lat': round(c['lat'] / c['n'], 5), 'lng': round(c['lng'] / c['n'], 5),
                    'count': c['count'], 'names': names})
    out.sort(key=lambda z: -z['count'])
    out = out[:top]
    peak = out[0]['count'] if out else 0
    for z in out:
        z['level'] = round(z['count'] / peak, 2) if peak else 0
    return out

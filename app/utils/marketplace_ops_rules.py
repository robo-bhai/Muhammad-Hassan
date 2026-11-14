"""Marketplace Operations dashboard ke pure rules (Django ka koi import nahi - seedha test ho sakte hain).

Thresholds yahan badalein; dashboard ke 'late' alerts aur rider states inhi se bante hain.
"""
from datetime import timedelta

NEW_LATE_MIN = 5          # vendor ne itne minute mein jawab nahi diya (pending)
PREP_GRACE_MIN = 10       # vendor ke batae prep time ke baad itni mohlat
PREP_DEFAULT_MIN = 20     # prep time na ho to yeh maan lein
READY_NO_RIDER_MIN = 5    # ready hai, rider assign nahi, itne minute se
TRANSIT_LATE_MIN = 45     # rider ne uthaya, itne minute se zyada ho gaye
RIDER_STALE_SEC = 120     # online rider ki last_seen itni purani ho to 'stale'

# Order ke stages (dashboard ke columns)
STAGE_NEW = 'new'               # vendor ke jawab ka intezar
STAGE_PREPARING = 'preparing'   # vendor tayyar kar raha hai
STAGE_READY = 'ready'           # tayyar, rider ka intezar / pickup
STAGE_ON_WAY = 'on_way'         # rider ke paas, raste mein
STAGES = [STAGE_NEW, STAGE_PREPARING, STAGE_READY, STAGE_ON_WAY]


def minutes_between(start, end):
    """Do datetimes ke beech minute (float, kam az kam 0). Koi None ho to None."""
    if start is None or end is None:
        return None
    return max((end - start).total_seconds() / 60.0, 0.0)


def order_stage(status, delivery_status=None):
    """SaleOrder.status (+ DeliveryInfo.status) se dashboard stage. Active na ho to None."""
    if status == 'pending':
        return STAGE_NEW
    if status in ('confirmed', 'processing'):
        return STAGE_PREPARING
    if status == 'ready':
        if delivery_status in ('picked_up', 'in_transit'):
            return STAGE_ON_WAY
        return STAGE_READY
    return None


def order_late_reason(stage, age_min, prep_min=None, has_rider=False,
                      since_ready_min=None, since_pickup_min=None):
    """Order late hai to wajah (text), warna None.

    age_min: order lagne se ab tak minute. since_ready_min / since_pickup_min: wo stage shuru
    hone se ab tak (pata ho to), warna age_min se kaam chalta hai."""
    if stage == STAGE_NEW:
        if age_min is not None and age_min >= NEW_LATE_MIN:
            return f'Vendor ne {int(age_min)}m se jawab nahi diya'
    elif stage == STAGE_PREPARING:
        limit = (prep_min or PREP_DEFAULT_MIN) + PREP_GRACE_MIN
        if age_min is not None and age_min >= limit:
            return f'Tayyari mein {int(age_min)}m (wada {int(prep_min or PREP_DEFAULT_MIN)}m)'
    elif stage == STAGE_READY:
        waited = since_ready_min if since_ready_min is not None else age_min
        if not has_rider and waited is not None and waited >= READY_NO_RIDER_MIN:
            return f'Rider nahi mila ({int(waited)}m se)'
    elif stage == STAGE_ON_WAY:
        t = since_pickup_min if since_pickup_min is not None else age_min
        if t is not None and t >= TRANSIT_LATE_MIN:
            return f'Raste mein {int(t)}m se'
    return None


def rider_state(is_active, is_online, last_seen_age_sec, open_deliveries):
    """'offline' | 'stale' | 'busy' | 'idle'."""
    if not is_active or not is_online:
        return 'offline'
    if last_seen_age_sec is None or last_seen_age_sec > RIDER_STALE_SEC:
        return 'stale'
    return 'busy' if open_deliveries else 'idle'


def percent(part, whole):
    """Fisad (0-100) ya None agar whole = 0."""
    return round(part * 100.0 / whole, 1) if whole else None


def commission_amount(sales, pct):
    """Sales par commission (2 decimals tak)."""
    return round(float(sales or 0) * float(pct or 0) / 100.0, 2)


def hourly_buckets(hours):
    """Hours (0-23 ki list) -> 24 ginti ki list."""
    out = [0] * 24
    for h in hours:
        if 0 <= h <= 23:
            out[h] += 1
    return out


def fmt_minutes(m):
    """67 -> '1h 07m', 25 -> '25m', None -> '-'."""
    if m is None:
        return '-'
    m = int(round(m))
    return f'{m // 60}h {m % 60:02d}m' if m >= 60 else f'{m}m'

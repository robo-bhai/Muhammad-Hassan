"""Vendor performance ke pure rules (Django ka koi import nahi - seedha test ho sakte hain).

Thresholds yahan badalein; report par laal 'nazar rakhein' flag inhi se banta hai.
"""
MIN_ORDERS = 5          # itne order se kam par rate/speed par flag nahi (kam data se galat nateeja)
CANCEL_WARN_PCT = 20.0  # cancel rate itna ya zyada
MIN_RATINGS = 3         # itni ratings se kam par rating flag nahi
LOW_RATING = 3.5        # isse kam average rating
DISPUTE_WARN = 3        # itne ya zyada disputes
SLOW_DELIVERY_MIN = 90  # order se delivery tak average itne minute ya zyada


def percent(part, whole):
    """Fisad (0-100) ya None agar whole = 0."""
    return round(part * 100.0 / whole, 1) if whole else None


def fmt_minutes(m):
    """67 -> '1h 07m', 25 -> '25m', None -> '-'."""
    if m is None:
        return '-'
    m = int(round(m))
    return f'{m // 60}h {m % 60:02d}m' if m >= 60 else f'{m}m'


def flags(row):
    """Is vendor par nazar rakhne ki wajahon ki list (khali = sab theek)."""
    out = []
    if row.get('orders', 0) >= MIN_ORDERS and row.get('cancel_rate') is not None \
            and row['cancel_rate'] >= CANCEL_WARN_PCT:
        out.append(f"Cancel {row['cancel_rate']:.0f}%")
    if row.get('rating_n', 0) >= MIN_RATINGS and row.get('rating') is not None \
            and row['rating'] < LOW_RATING:
        out.append(f"Rating {row['rating']:.1f}")
    if row.get('disputes', 0) >= DISPUTE_WARN:
        out.append(f"{row['disputes']} disputes")
    if row.get('delivered', 0) >= MIN_ORDERS and row.get('delivery_min') is not None \
            and row['delivery_min'] >= SLOW_DELIVERY_MIN:
        out.append(f"Slow delivery {fmt_minutes(row['delivery_min'])}")
    return out

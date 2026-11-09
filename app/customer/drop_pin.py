"""Customer ki delivery location ka pin (session mein, sirf 3 ghante). Order banate waqt SaleOrder mein jata hai."""
import time
from decimal import Decimal

SESSION_KEY = 'drop_pin'
MAX_AGE_SECONDS = 3 * 3600


def save_pin(session, lat, lng, now_ts=None):
    session[SESSION_KEY] = {'lat': str(lat), 'lng': str(lng), 'at': int(now_ts or time.time())}
    session.modified = True


def order_fields(session, now_ts=None):
    """SaleOrder.objects.create(...) mein lagane wali fields (pin purana ya na ho to khali)."""
    d = session.get(SESSION_KEY)
    if not d:
        return {}
    if (now_ts or time.time()) - d.get('at', 0) > MAX_AGE_SECONDS:
        return {}
    try:
        return {'delivery_lat': Decimal(d['lat']), 'delivery_lng': Decimal(d['lng'])}
    except Exception:
        return {}

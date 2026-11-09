"""Customer ke delivery pin ka session logic (pure Python)."""
import pathlib
import time
from decimal import Decimal

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'app' / 'customer' / 'drop_pin.py').read_text()
_NS = {}
exec(_SRC, _NS)


class _Sess(dict):
    modified = False


def test_fresh_pin_goes_to_order():
    s = _Sess()
    _NS['save_pin'](s, Decimal('26.2235000'), Decimal('50.5876000'), now_ts=1000)
    f = _NS['order_fields'](s, now_ts=1000 + 60)
    assert f == {'delivery_lat': Decimal('26.2235000'), 'delivery_lng': Decimal('50.5876000')}
    assert s.modified


def test_old_or_missing_pin_ignored():
    s = _Sess()
    assert _NS['order_fields'](s) == {}
    _NS['save_pin'](s, 26.2, 50.5, now_ts=1000)
    assert _NS['order_fields'](s, now_ts=1000 + 3 * 3600 + 1) == {}


def test_broken_session_data_ignored():
    assert _NS['order_fields']({'drop_pin': {'lat': 'x', 'lng': 'y', 'at': time.time()}}) == {}

"""Auto dispatch ki tarteeb (pure Python; Django ki zaroorat nahi)."""
import math
import pathlib
from datetime import timedelta

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'app' / 'customer' / 'dispatch.py').read_text()
_PURE = _SRC[_SRC.index('WINDOW_SECONDS = 20'):_SRC.index('# ---------------- DB wala hissa')]
_NS = {'math': math, 'timedelta': timedelta}
exec(_PURE, _NS)
rank_candidates, is_visible, haversine_km = _NS['rank_candidates'], _NS['is_visible'], _NS['haversine_km']


def test_haversine_roughly_right():
    assert abs(haversine_km(26.2235, 50.5876, 26.2235, 50.6876) - 10.0) < 0.3


def test_nearest_first_and_load_penalty():
    c = [{'id': 1, 'lat': 26.230, 'lng': 50.58, 'active': 0},   # door
         {'id': 2, 'lat': 26.224, 'lng': 50.58, 'active': 0},   # nazdeek
         {'id': 3, 'lat': 26.224, 'lng': 50.58, 'active': 3}]   # nazdeek lekin 3 orders
    assert rank_candidates(c, 26.2235, 50.58) == [2, 1, 3]


def test_without_store_coords_uses_load():
    c = [{'id': 5, 'lat': None, 'lng': None, 'active': 2},
         {'id': 4, 'lat': None, 'lng': None, 'active': 0}]
    assert rank_candidates(c, None, None) == [4, 5]


def test_located_riders_before_unlocated():
    c = [{'id': 1, 'lat': None, 'lng': None, 'active': 0},
         {'id': 2, 'lat': 26.3, 'lng': 50.6, 'active': 0}]
    assert rank_candidates(c, 26.2, 50.5) == [2, 1]


def test_waterfall_visibility():
    rk = [10, 20, 30]
    assert is_visible(10, rk, [], 0)
    assert not is_visible(20, rk, [], 10)
    assert is_visible(20, rk, [], 20)
    assert not is_visible(30, rk, [], 39)
    assert is_visible(30, rk, [], 40)


def test_open_pool_and_declines():
    rk = [10, 20]
    assert not is_visible(99, rk, [], 30)      # ranked nahi, abhi intezar
    assert is_visible(99, rk, [], 90)          # 90s baad sab ko
    assert not is_visible(10, rk, [10], 100)   # reject karne wale ko dobara nahi
    assert is_visible(99, rk, [10, 20], 1)     # saare ranked riders ne reject kiya -> open
    assert is_visible(7, [], [], 0)            # koi eligible nahi tha -> open pool

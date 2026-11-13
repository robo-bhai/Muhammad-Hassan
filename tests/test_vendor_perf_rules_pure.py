"""Pure tests (no Django):  python tests/test_vendor_perf_rules_pure.py"""
import importlib.util
import os

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'vendor_perf_rules.py')
_s = importlib.util.spec_from_file_location('vendor_perf_rules', _p)
r = importlib.util.module_from_spec(_s)
_s.loader.exec_module(r)

OK = dict(orders=20, delivered=18, cancel_rate=10.0, rating=4.6, rating_n=12, disputes=0, delivery_min=45)


def test_percent():
    assert r.percent(1, 4) == 25.0
    assert r.percent(0, 10) == 0.0
    assert r.percent(5, 0) is None


def test_fmt_minutes():
    assert r.fmt_minutes(None) == '-'
    assert r.fmt_minutes(25) == '25m'
    assert r.fmt_minutes(67) == '1h 07m'
    assert r.fmt_minutes(120) == '2h 00m'


def test_healthy_vendor_has_no_flags():
    assert r.flags(OK) == []


def test_high_cancel_rate_flagged_only_with_enough_orders():
    assert r.flags({**OK, 'cancel_rate': 30.0}) == ['Cancel 30%']
    assert r.flags({**OK, 'orders': 3, 'cancel_rate': 66.0}) == []        # kam data


def test_low_rating_needs_enough_ratings():
    assert r.flags({**OK, 'rating': 2.8}) == ['Rating 2.8']
    assert r.flags({**OK, 'rating': 2.0, 'rating_n': 2}) == []
    assert r.flags({**OK, 'rating': None, 'rating_n': 0}) == []


def test_disputes_and_slow_delivery():
    assert r.flags({**OK, 'disputes': 3}) == ['3 disputes']
    assert r.flags({**OK, 'delivery_min': 95}) == ['Slow delivery 1h 35m']
    assert r.flags({**OK, 'delivered': 2, 'delivery_min': 200}) == []


def test_multiple_flags_and_missing_keys():
    f = r.flags({**OK, 'cancel_rate': 25.0, 'rating': 3.0, 'disputes': 4})
    assert len(f) == 3
    assert r.flags({}) == []


if __name__ == '__main__':
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn(); n += 1
            print('ok ', name)
    print(n, 'tests passed')

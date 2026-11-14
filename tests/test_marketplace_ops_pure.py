"""Pure tests (no Django):  python tests/test_marketplace_ops_pure.py"""
import importlib.util
import os
from datetime import datetime, timedelta

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'marketplace_ops_rules.py')
_s = importlib.util.spec_from_file_location('marketplace_ops_rules', _p)
r = importlib.util.module_from_spec(_s)
_s.loader.exec_module(r)


def test_order_stage():
    assert r.order_stage('pending') == r.STAGE_NEW
    assert r.order_stage('confirmed') == r.STAGE_PREPARING
    assert r.order_stage('processing', 'pending') == r.STAGE_PREPARING
    assert r.order_stage('ready') == r.STAGE_READY
    assert r.order_stage('ready', 'assigned') == r.STAGE_READY
    assert r.order_stage('ready', 'picked_up') == r.STAGE_ON_WAY
    assert r.order_stage('ready', 'in_transit') == r.STAGE_ON_WAY
    assert r.order_stage('delivered') is None
    assert r.order_stage('cancelled') is None


def test_late_new():
    assert r.order_late_reason(r.STAGE_NEW, 4) is None
    assert r.order_late_reason(r.STAGE_NEW, 5)


def test_late_preparing_uses_prep_minutes():
    assert r.order_late_reason(r.STAGE_PREPARING, 29, prep_min=20) is None
    assert r.order_late_reason(r.STAGE_PREPARING, 30, prep_min=20)
    assert r.order_late_reason(r.STAGE_PREPARING, 29, prep_min=None) is None   # default 20 + 10
    assert r.order_late_reason(r.STAGE_PREPARING, 30, prep_min=None)


def test_late_ready_needs_rider():
    assert r.order_late_reason(r.STAGE_READY, 30, has_rider=True) is None
    assert r.order_late_reason(r.STAGE_READY, 30, has_rider=False, since_ready_min=2) is None
    assert r.order_late_reason(r.STAGE_READY, 30, has_rider=False, since_ready_min=5)


def test_late_on_way():
    assert r.order_late_reason(r.STAGE_ON_WAY, 80, since_pickup_min=44) is None
    assert r.order_late_reason(r.STAGE_ON_WAY, 80, since_pickup_min=45)


def test_late_none_stage_or_age():
    assert r.order_late_reason(None, 999) is None
    assert r.order_late_reason(r.STAGE_NEW, None) is None


def test_rider_state():
    assert r.rider_state(True, False, 5, 0) == 'offline'
    assert r.rider_state(False, True, 5, 0) == 'offline'
    assert r.rider_state(True, True, None, 0) == 'stale'
    assert r.rider_state(True, True, 121, 2) == 'stale'
    assert r.rider_state(True, True, 30, 0) == 'idle'
    assert r.rider_state(True, True, 30, 1) == 'busy'


def test_minutes_between():
    a = datetime(2026, 1, 1, 12, 0)
    assert r.minutes_between(a, a + timedelta(minutes=30)) == 30
    assert r.minutes_between(a, a - timedelta(minutes=5)) == 0
    assert r.minutes_between(None, a) is None


def test_percent_commission_hourly_fmt():
    assert r.percent(1, 4) == 25.0 and r.percent(1, 0) is None
    assert r.commission_amount(1000, 12.5) == 125.0
    assert r.commission_amount(None, 10) == 0.0
    b = r.hourly_buckets([0, 0, 13, 23, 99, -1])
    assert len(b) == 24 and b[0] == 2 and b[13] == 1 and b[23] == 1 and sum(b) == 4
    assert r.fmt_minutes(None) == '-' and r.fmt_minutes(67) == '1h 07m' and r.fmt_minutes(25) == '25m'


if __name__ == '__main__':
    n = 0
    for k, v in list(globals().items()):
        if k.startswith('test_'):
            v(); n += 1
    print(f'{n} tests OK')

"""Pure tests (no Django):  python tests/test_dispatch_board_pure.py"""
import importlib.util
import os

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'dispatch_board_rules.py')
_s = importlib.util.spec_from_file_location('dispatch_board_rules', _p)
r = importlib.util.module_from_spec(_s)
_s.loader.exec_module(r)

STORE = (26.2285, 50.5860)


def rider(i, lat, lng, open_n=0, state='idle'):
    return {'id': i, 'state': state, 'open': open_n, 'lat': lat, 'lng': lng}


def test_board_column():
    assert r.board_column('ready', 'pending', False) == r.COL_NEEDS
    assert r.board_column('ready', 'assigned', True) == r.COL_ASSIGNED
    assert r.board_column('ready', 'picked_up', True) is None
    assert r.board_column('ready', 'in_transit', True) is None
    assert r.board_column('confirmed', None, False) == r.COL_PREPARING
    assert r.board_column('processing', 'pending', False) == r.COL_PREPARING
    assert r.board_column('pending', None, False) is None
    assert r.board_column('delivered', 'delivered', True) is None


def test_can_assign():
    assert r.can_assign('ready', 'pending')[0]
    assert r.can_assign('ready', 'assigned')[0]           # reassign allowed before pickup
    assert not r.can_assign('ready', 'picked_up')[0]
    assert not r.can_assign('confirmed', None)[0]
    assert r.can_assign('cancelled', None)[1]


def test_suggest_nearest_first():
    near, far = rider(1, 26.2300, 50.5870), rider(2, 26.3000, 50.6500)
    out = r.suggest_riders(*STORE, [far, near])
    assert [x['id'] for x in out] == [1, 2]
    assert out[0]['dist_km'] < out[1]['dist_km']
    assert out[0]['eta_min'] >= 1


def test_suggest_load_penalty():
    # thora door par khali rider, nazdeek par 2 orders wale se behtar
    busy_near = rider(1, 26.2290, 50.5865, open_n=2, state='busy')
    free_a_bit_far = rider(2, 26.2400, 50.5900, open_n=0)
    out = r.suggest_riders(*STORE, [busy_near, free_a_bit_far])
    assert out[0]['id'] == 2


def test_suggest_full_riders_last_and_flagged():
    full = rider(1, 26.2286, 50.5861, open_n=3, state='busy')
    ok = rider(2, 26.3000, 50.6500)
    out = r.suggest_riders(*STORE, [full, ok])
    assert [x['id'] for x in out] == [2, 1]
    assert out[1]['full'] and not out[0]['full']


def test_suggest_skips_offline_and_stale():
    out = r.suggest_riders(*STORE, [rider(1, 26.2, 50.5, state='offline'), rider(2, 26.2, 50.5, state='stale')])
    assert out == []


def test_suggest_without_location_goes_last_but_listed():
    nolocation = {'id': 1, 'state': 'idle', 'open': 0, 'lat': None, 'lng': None}
    located = rider(2, 26.3, 50.65)
    out = r.suggest_riders(*STORE, [nolocation, located])
    assert [x['id'] for x in out] == [2, 1]
    assert out[1]['dist_km'] is None and out[1]['eta_min'] is None


def test_suggest_store_without_location():
    out = r.suggest_riders(None, None, [rider(1, 26.2, 50.5, open_n=1), rider(2, 26.3, 50.6, open_n=0)])
    assert [x['id'] for x in out] == [2, 1]      # sirf load se


def test_limit_and_no_mutation():
    rs = [rider(i, 26.2 + i / 1000, 50.5) for i in range(1, 9)]
    snapshot = [dict(x) for x in rs]
    assert len(r.suggest_riders(*STORE, rs)) == r.MAX_SUGGESTIONS
    assert rs == snapshot


def test_eta():
    assert r.eta_minutes(None) is None
    assert r.eta_minutes(0.1) == 1
    assert r.eta_minutes(10) == 30


if __name__ == '__main__':
    n = 0
    for k, v in list(globals().items()):
        if k.startswith('test_'):
            v(); n += 1
    print(f'{n} tests OK')

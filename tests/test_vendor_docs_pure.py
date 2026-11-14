"""Pure tests (no Django):  python tests/test_vendor_docs_pure.py"""
import importlib.util
import os
from datetime import date, timedelta

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'customer', 'vendor_docs.py')
_s = importlib.util.spec_from_file_location('vendor_docs', _p)
v = importlib.util.module_from_spec(_s)
_s.loader.exec_module(v)

TODAY = date(2026, 11, 14)
FUTURE = TODAY + timedelta(days=365)


def doc(kind, status='approved', expiry=FUTURE):
    return {'kind': kind, 'status': status, 'expiry': expiry}


FULL = [doc('cr'), doc('owner_id'), doc('bank', expiry=None)]


def test_constants():
    assert v.REQUIRED == ['cr', 'owner_id', 'bank']
    assert v.NEEDS_EXPIRY == {'cr', 'owner_id', 'health'}
    assert v.NEEDS_NUMBER == {'cr', 'owner_id', 'vat'}


def test_empty_all_required_missing():
    ev = v.evaluate([], TODAY)
    assert ev['missing'] == ['cr', 'owner_id', 'bank'] and not ev['complete']


def test_complete():
    ev = v.evaluate(FULL, TODAY)
    assert ev['complete'] and not v.blocking(ev) and not ev['missing']


def test_pending_or_rejected_not_complete():
    ev = v.evaluate([doc('cr', 'pending'), doc('owner_id'), doc('bank', expiry=None)], TODAY)
    assert not ev['complete'] and ev['pending'] == ['cr']
    ev = v.evaluate([doc('cr', 'rejected'), doc('owner_id'), doc('bank', expiry=None)], TODAY)
    assert not ev['complete'] and v.blocking(ev) == ['cr']


def test_expired_blocks_and_breaks_complete():
    ev = v.evaluate([doc('cr', expiry=TODAY - timedelta(days=1)), doc('owner_id'), doc('bank', expiry=None)], TODAY)
    assert ev['expired'] == ['cr'] and not ev['complete'] and v.blocking(ev) == ['cr']


def test_expiring_soon_boundaries():
    soon = v.evaluate([doc('cr', expiry=TODAY + timedelta(days=30))] + FULL[1:], TODAY)
    assert soon['expiring'] == ['cr'] and soon['complete']          # abhi valid hai
    later = v.evaluate([doc('cr', expiry=TODAY + timedelta(days=31))] + FULL[1:], TODAY)
    assert later['expiring'] == []
    today_exp = v.evaluate([doc('cr', expiry=TODAY)] + FULL[1:], TODAY)
    assert today_exp['expiring'] == ['cr'] and not today_exp['expired']   # aaj tak valid


def test_optional_not_missing_but_checked_when_uploaded():
    assert 'vat' not in v.evaluate(FULL, TODAY)['missing']
    ev = v.evaluate(FULL + [doc('health', expiry=TODAY - timedelta(days=2))], TODAY)
    assert ev['expired'] == ['health'] and not ev['complete']
    ev = v.evaluate(FULL + [doc('vat', 'pending', None)], TODAY)
    assert ev['complete'] and ev['pending'] == ['vat']             # optional pending se complete nahi rukta


def test_unknown_kind_ignored_and_bad_status_is_pending():
    ev = v.evaluate(FULL + [{'kind': 'zzz', 'status': 'approved', 'expiry': None}], TODAY)
    assert ev['complete']
    ev = v.evaluate([{'kind': 'cr', 'status': 'weird', 'expiry': FUTURE}], TODAY)
    assert ev['pending'] == ['cr']


def test_summary_and_warnings():
    ev = v.evaluate([doc('cr', expiry=TODAY + timedelta(days=5)), doc('owner_id', 'rejected')], TODAY)
    s = v.summary(ev)
    assert s.startswith('1/3 approved') and '1 rejected' in s and '1 missing' in s and '1 expiring' in s
    w = v.warnings(ev)
    assert ('danger', 'Owner CPR / ID card was rejected - please upload it again.') in w
    assert ('warning', 'Commercial Registration (CR) expires soon.') in w
    exp = v.evaluate([doc('cr', 'rejected', TODAY - timedelta(days=1))], TODAY)
    texts = [t for _l, t in v.warnings(exp)]
    assert sum('Commercial Registration' in t for t in texts) == 1       # expire + rejected ek hi dafa


if __name__ == '__main__':
    n = 0
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            f(); n += 1
    print(f'{n} tests OK')

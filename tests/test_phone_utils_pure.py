"""Pure tests (no Django):  python -m pytest tests/test_phone_utils_pure.py   (ya seedha python se chalayein)
app/utils/phone_utils.py ko seedha file se load karta hai."""
import importlib.util
import os

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'phone_utils.py')
_s = importlib.util.spec_from_file_location('phone_utils', _p)
pu = importlib.util.module_from_spec(_s)
_s.loader.exec_module(pu)


def test_all_pakistani_formats_give_same_key():
    for raw in ['03001234567', '0300-1234567', '0300 1234567', '+923001234567', '+92 300 1234567',
                '923001234567', '92-300-1234567', '3001234567', '00923001234567', '(0300) 123 4567']:
        assert pu.phone_key(raw) == '923001234567', raw


def test_different_numbers_stay_different():
    assert pu.phone_key('03001234567') != pu.phone_key('03001234568')
    assert pu.phone_key('03001234567') != pu.phone_key('03111234567')


def test_empty_and_junk():
    assert pu.phone_key('') == ''
    assert pu.phone_key(None) == ''
    assert pu.phone_key('N/A') == ''
    assert not pu.is_comparable('123')          # bohat chhota
    assert not pu.is_comparable('')


def test_foreign_number_not_forced_to_pakistan():
    assert pu.phone_key('+44 7911 123456') == '447911123456'
    assert pu.phone_key('+44 7911 123456') != pu.phone_key('03001234567')


def test_landline():
    assert pu.phone_key('042-35761234') == '924235761234'
    assert pu.phone_key('+92 42 35761234') == '924235761234'


def test_same_phone_and_changed():
    assert pu.same_phone('0300-1234567', '+923001234567')
    assert not pu.same_phone('', '')
    assert not pu.phone_changed('0300-1234567', '+92 300 1234567')   # sirf format badla
    assert pu.phone_changed('03001234567', '03001234568')


def test_matches_shop_normalize_phone():
    # views_customer_auth.normalize_phone ki nakal: dono ka nateeja '+' + key hona chahiye
    def shop(phone):
        phone = phone.replace(' ', '').replace('-', '').replace('+', '')
        if phone.startswith('92'):
            phone = phone[2:]
        elif phone.startswith('0'):
            phone = phone[1:]
        return f'+92{phone}'
    for raw in ['03001234567', '0300-1234567', '+923001234567', '923001234567']:
        assert shop(raw) == '+' + pu.phone_key(raw)


class _Obj:
    def __init__(self, pk, phone): self.pk, self.contact_number = pk, phone


class _QS(list):
    def filter(self, **kw):
        (k, v), = kw.items()
        if k.endswith('__contains'): return _QS(o for o in self if v in (o.contact_number or ''))
        return self
    def exclude(self, *a, **kw):
        if 'pk' in kw: return _QS(o for o in self if o.pk != kw['pk'])
        return _QS(o for o in self if o.contact_number != '')


class _Model:
    rows = _QS([_Obj(1, '0300-1234567'), _Obj(2, '+923111234567'), _Obj(3, ''), _Obj(4, '03001234567')])
    class objects:
        @staticmethod
        def filter(**kw): return _Model.rows
        @staticmethod
        def exclude(**kw): return _Model.rows


def test_find_by_phone_across_formats():
    hits = pu.find_by_phone(_Model, '+92 300 1234567')
    assert sorted(o.pk for o in hits) == [1, 4]
    assert [o.pk for o in pu.find_by_phone(_Model, '+92 300 1234567', exclude_pk=1)] == [4]
    assert pu.find_by_phone(_Model, '123') == []


def test_group_duplicates():
    rows = [{'id': 1, 'p': '0300-1234567'}, {'id': 2, 'p': '+923001234567'}, {'id': 3, 'p': '03111234567'}]
    g = pu.group_duplicates(rows, lambda r: pu.phone_key(r['p']))
    assert len(g) == 1 and [r['id'] for r in g[0]['rows']] == [1, 2]


if __name__ == '__main__':
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn(); n += 1
            print('ok ', name)
    print(n, 'tests passed')

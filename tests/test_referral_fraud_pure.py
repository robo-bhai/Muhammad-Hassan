"""Referral fraud checks ke pure helper (phone / address ka muqabla, mahine ki shuruaat). Django ki zaroorat nahi."""
import datetime
import pathlib
import re

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'app' / 'customer' / 'referrals.py').read_text(encoding='utf-8')
_FN = _SRC[_SRC.index('MIN_ADDRESS_LEN ='):_SRC.index('def _phones')]


class _TZ:                       # timezone ka chhota nakli: sirf wahi cheezen jo month_start use karta hai
    now = staticmethod(lambda: datetime.datetime(2026, 11, 12, 18, 30, 5, 123))
    is_aware = staticmethod(lambda dt: dt.tzinfo is not None)
    localtime = staticmethod(lambda dt: dt)


_NS = {'re': re, 'timezone': _TZ}
exec(_FN, _NS)
phone_key, address_key, month_start = _NS['phone_key'], _NS['address_key'], _NS['month_start']


def test_phone_formats_match():
    assert phone_key('+923001234567') == phone_key('0300 1234567') == phone_key('92-300-1234567') == '3001234567'
    assert phone_key('03001234567') != phone_key('03001234568')


def test_phone_too_short_or_empty_never_matches():
    assert phone_key(None) == '' and phone_key('') == '' and phone_key('123') == ''


def test_address_ignores_case_and_punctuation():
    a = address_key('House 12, Street 5, Gulberg III,  Lahore')
    b = address_key('house 12 street 5 gulberg iii lahore')
    assert a and a == b


def test_address_different_or_too_short():
    assert address_key('House 12, Street 5, Lahore') != address_key('House 14, Street 5, Lahore')
    assert address_key('ghar') == '' and address_key(None) == ''


def test_month_start():
    assert month_start() == datetime.datetime(2026, 11, 1, 0, 0)
    assert month_start(datetime.datetime(2026, 12, 31, 23, 59)) == datetime.datetime(2026, 12, 1, 0, 0)

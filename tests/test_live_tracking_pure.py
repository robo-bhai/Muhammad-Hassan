"""Live tracking: location ki jaanch (pure Python; Django ki zaroorat nahi)."""
import math
import pathlib
from decimal import Decimal

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'app' / 'customer' / 'views_live_tracking.py').read_text()
_FN = _SRC[_SRC.index('def parse_coords'):_SRC.index('@rider_login_required')]
_NS = {'math': math, 'Decimal': Decimal}
exec(_FN, _NS)
parse_coords = _NS['parse_coords']


def test_valid_coords():
    assert parse_coords('26.2235', '50.5876') == (Decimal('26.2235'), Decimal('50.5876'))
    assert parse_coords(26.22351234567, 50.5) == (Decimal('26.2235123'), Decimal('50.5'))


def test_rejects_bad_values():
    for bad in [(None, None), ('abc', '1'), ('91', '10'), ('10', '181'),
                ('nan', '1'), ('inf', '1'), ('0', '0'), ('', '')]:
        assert parse_coords(*bad) is None

"""Loyalty points ka hisaab (pure Python; Django ki zaroorat nahi)."""
import pathlib
from decimal import ROUND_DOWN, Decimal

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'app' / 'customer' / 'offers.py').read_text()
_FN = _SRC[_SRC.index('def points_from_amount'):_SRC.index('def points_balance')]
_NS = {'Decimal': Decimal, 'ROUND_DOWN': ROUND_DOWN}
exec(_FN, _NS)
points_from_amount = _NS['points_from_amount']


def test_whole_points_only():
    assert points_from_amount(1250, 1) == 12
    assert points_from_amount(99, 1) == 0
    assert points_from_amount(100, 1) == 1
    assert points_from_amount(Decimal('1999.99'), 1) == 19


def test_rate_and_edge_cases():
    assert points_from_amount(1250, Decimal('2.5')) == 31
    assert points_from_amount(0, 1) == 0
    assert points_from_amount(-50, 1) == 0
    assert points_from_amount(500, 0) == 0
    assert points_from_amount(None, 1) == 0

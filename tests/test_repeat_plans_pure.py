"""Repeat orders: pure schedule maths + wiring (Django ki zaroorat nahi)."""
import ast
import importlib.util
import pathlib
from datetime import datetime, time

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def _next_occurrence():
    """repeat_plans.py se sirf pure function nikaal kar chalao (module imports Django)."""
    src = _read('app', 'customer', 'repeat_plans.py')
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == 'next_occurrence')
    ns = {'datetime': datetime, 'timedelta': __import__('datetime').timedelta}
    exec(compile(ast.Module([fn], []), 'x', 'exec'), ns)
    return ns['next_occurrence']


def test_daily_goes_to_today_or_tomorrow():
    f = _next_occurrence()
    assert f(datetime(2026, 11, 13, 6, 0), 'daily', 0, time(8, 0)) == datetime(2026, 11, 13, 8, 0)
    assert f(datetime(2026, 11, 13, 9, 0), 'daily', 0, time(8, 0)) == datetime(2026, 11, 14, 8, 0)
    assert f(datetime(2026, 11, 13, 8, 0), 'daily', 0, time(8, 0)) == datetime(2026, 11, 14, 8, 0)   # barabar = agla din


def test_weekly_lands_on_chosen_weekday():
    f = _next_occurrence()
    fri = datetime(2026, 11, 13, 10, 0)                      # Friday
    assert f(fri, 'weekly', 4, time(8, 0)) == datetime(2026, 11, 20, 8, 0)   # Friday guzar chuka -> agla hafta
    assert f(fri, 'weekly', 5, time(8, 0)) == datetime(2026, 11, 14, 8, 0)   # Saturday kal
    assert f(fri, 'weekly', 0, time(8, 0)) == datetime(2026, 11, 16, 8, 0)   # Monday
    assert f(fri, 'weekly', 4, time(18, 0)) == datetime(2026, 11, 13, 18, 0)  # aaj shaam


def test_wiring():
    models_init = _read('app', 'models', '__init__.py')
    assert '"trade.repeat_plans"' in models_init
    urls = _read('app', 'urls.py')
    for name in ('repeat_plans', 'repeat_plan_create', 'repeat_plan_toggle', 'repeat_plan_delete', 'repeat_plan_run'):
        assert f"name='{name}'" in urls, name
    views = _read('app', 'customer', 'views_repeat.py')
    assert 'customer=customer' in views and 'customer=_customer(request)' in views     # sirf apne plans
    assert 'build_cart_from_order' in views and 'def build_cart_from_order' in _read('app', 'customer', 'views_reorder.py')
    assert "RepeatOrderPlan" in _read('app', 'migrations', '0082_repeat_order_plans.py')
    assert 'repeat_plan_create' in _read('templates', 'customer_portal', 'order_detail.html')

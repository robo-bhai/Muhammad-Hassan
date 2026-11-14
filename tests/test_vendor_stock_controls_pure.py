"""Vendor stock controls: hide sold-out + apni low-stock hadd (pure wiring checks)."""
import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def test_effective_level_prefers_vendor_value():
    src = _read('app', 'customer', 'stock_alerts.py')
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == 'effective_level')
    ns = {}
    exec(compile(ast.Module([fn], []), 'x', 'exec'), ns)
    f = ns['effective_level']

    class P:  # profile jaisa
        def __init__(self, v): self.low_stock_level = v
    assert f(P(None), {'level': 5}) == 5
    assert f(P(12), {'level': 5}) == 12
    assert f(P(0), {'level': 5}) == 5          # 0 = khali


def test_hide_sold_out_only_for_opted_in_vendors_and_zero_stock():
    src = _read('app', 'customer', 'stock_alerts.py')
    body = src[src.index('def hide_sold_out'):src.index('def _already_sent')]
    assert 'vendor__portal_profile__hide_sold_out=True' in body    # sirf jinhon ne option chalu kiya
    assert 't__gt=0' in body and 'exclude(pk__in=in_stock)' in body  # stock > 0 wale nahi chhupte


def test_applied_on_store_page_and_home():
    assert 'hide_sold_out(base)' in _read('app', 'customer', 'views_stores.py')
    home = _read('app', 'customer', 'views_customer_portal.py')
    assert 'products = hide_sold_out(products)' in home


def test_model_migration_settings():
    model = _read('app', 'models', 'trade', 'vendor_portal.py')
    assert 'hide_sold_out = models.BooleanField(' in model and 'low_stock_level = models.PositiveSmallIntegerField(' in model
    mig = _read('app', 'migrations', '0085_vendor_stock_controls.py')
    assert "('app', '0084_vendor_auto_accept')" in mig and "name='hide_sold_out'" in mig and "name='low_stock_level'" in mig
    view = _read('app', 'customer', 'views_vendor_portal.py')
    assert 'profile.hide_sold_out, profile.low_stock_level = hide_sold_out, low_level' in view
    assert 'effective_level(profile, stock_cfg)' in view
    tpl = _read('templates', 'customer_portal', 'vendor', 'store_settings.html')
    assert 'name="hide_sold_out"' in tpl and 'name="low_stock_level"' in tpl

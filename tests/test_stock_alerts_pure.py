"""Vendor low-stock / sold-out alerts: wiring + logic check (pure Python; Django ki zaroorat nahi)."""
import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def _stock_state():
    tree = ast.parse(_read('app', 'customer', 'stock_alerts.py'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'stock_state')
    ns = {}
    exec(compile(ast.Module([fn], []), 'x', 'exec'), ns)
    return ns['stock_state']


def test_stock_state_levels():
    f = _stock_state()
    assert f(0, 5) == 'out' and f(-2, 5) == 'out' and f(None, 5) == 'out'
    assert f(1, 5) == 'low' and f(5, 5) == 'low'
    assert f(5.5, 5) == 'ok' and f(40, 5) == 'ok'


def test_flag_and_settings():
    flags = None
    for node in ast.parse(_read('app', 'module_config', 'shop_flags.py')).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'FLAGS':
            flags = ast.literal_eval(node.value)
    assert flags['vendor_low_stock_alert_enabled'][0] is True
    cat = _read('app', 'module_config', 'settings_catalog.py')
    assert "'name': 'vendor_low_stock_alert_enabled'" in cat and "'name': 'vendor_low_stock_level'" in cat


def test_signal_registered_and_safe():
    assert b'import app.customer.stock_alerts' in (_ROOT / 'app' / 'apps.py').read_bytes()
    src = _read('app', 'customer', 'stock_alerts.py')
    assert "sender='app.Inventory'" in src and 'transaction.on_commit' in src
    assert 'created' in src                 # naye zero-stock row par jhoota alert nahi
    assert 'approval_status=\'approved\'' in src and 'is_active=True' in src


def test_dashboard_and_store_menu():
    view = _read('app', 'customer', 'views_vendor_portal.py')
    assert 'stock_state' in view and "'low_count'" in view
    tpl = _read('templates', 'customer_portal', 'vendor', 'dashboard.html')
    assert 'Sold out (auto)' in tpl and 'Low stock' in tpl
    assert "'sold_out', 'name'" in _read('app', 'customer', 'views_stores.py')

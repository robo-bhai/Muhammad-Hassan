"""Sponsored / Featured store: wiring check (pure Python; Django ki zaroorat nahi)."""
import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_APP = _ROOT / 'app'
_TPL = _ROOT / 'templates' / 'customer_portal'


def _flags():
    src = (_APP / 'module_config' / 'shop_flags.py').read_text()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'FLAGS':
            return ast.literal_eval(node.value)
    raise AssertionError('FLAGS not found')


def test_flag_exists():
    default, message = _flags()['shop_sponsored_enabled']
    assert isinstance(default, bool) and message


def test_settings_are_in_catalog():
    src = (_APP / 'module_config' / 'settings_catalog.py').read_text()
    for name in ('shop_sponsored_enabled', 'sponsored_price', 'sponsored_days', 'sponsored_max_slots'):
        assert f"'name': '{name}'" in src, name


def test_settings_keys_match_helper():
    src = (_APP / 'customer' / 'sponsored.py').read_text()
    for name in ('sponsored_price', 'sponsored_days', 'sponsored_max_slots', 'shop_sponsored_enabled'):
        assert name in src, name


def test_route_view_and_templates():
    assert "name='vendor_promote'" in (_APP / 'urls.py').read_text()
    assert 'def vendor_promote' in (_APP / 'customer' / 'views_vendor_tools.py').read_text()
    assert (_TPL / 'vendor' / 'promote.html').exists()
    assert 'st.sponsored' in (_TPL / 'shop.html').read_text()
    assert 's.sponsored' in (_TPL / 'stores.html').read_text()


def test_closed_store_never_outranks_open():
    src = (_APP / 'customer' / 'views_stores.py').read_text()
    assert "STATUS_ORDER[s.status], 0 if s.sponsored else 1" in src


def test_migration_follows_previous():
    src = (_APP / 'migrations' / '0074_store_sponsorship.py').read_text()
    assert "'0073_enable_pro_loyalty'" in src and "name='StoreSponsorship'" in src

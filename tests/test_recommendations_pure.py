"""Personal recommendations: wiring check (pure Python; Django ki zaroorat nahi)."""
import ast
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def test_flag_and_settings():
    flags = None
    for n in ast.parse(_read('app', 'module_config', 'shop_flags.py')).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'FLAGS':
            flags = ast.literal_eval(n.value)
    assert flags['shop_recommendations_enabled'][0] is True
    cat = _read('app', 'module_config', 'settings_catalog.py')
    for name in ('shop_recommendations_enabled', 'reco_trending_days', 'reco_trending_min_orders'):
        assert f"'name': '{name}'" in cat, name
    src = _read('app', 'customer', 'recommendations.py')
    for name in ('shop_recommendations_enabled', 'reco_trending_days', 'reco_trending_min_orders'):
        assert name in src, name


def test_only_live_stock_and_open_stores_are_recommended():
    src = _read('app', 'customer', 'recommendations.py')
    assert "is_active=True, approval_status='approved'" in src
    assert 'total_stock__gt=0' in src
    assert "status_label == 'closed'" in src
    assert ".exclude(order__status='cancelled')" in src          # trending mein cancel orders nahi
    assert 'DONE_STATUSES' in src                                # favourites / reorder sirf poore hue orders se


def test_personal_rows_use_own_orders_only():
    src = _read('app', 'customer', 'recommendations.py')
    assert 'order__customer=customer' in src and 'customer=customer, status__in=DONE_STATUSES' in src
    assert 'customer_profile' in src                             # guest ko sirf trending


def test_home_wiring_and_template():
    view = _read('app', 'customer', 'views_customer_portal.py')
    assert "'reco': _home_reco(request, search, category_id, brand_id)" in view
    assert "from .recommendations import home_rows" in view
    tpl = _read('templates', 'customer_portal', 'shop.html')
    assert "{% url 'reorder' o.order_id %}" in tpl
    assert 'reco.favourites' in tpl and 'reco.trending' in tpl and 'reco.reorder' in tpl
    assert 'csrf_token' in tpl[tpl.index('reco.reorder'):tpl.index('reco.favourites')]


def test_errors_never_break_home():
    src = _read('app', 'customer', 'recommendations.py')
    assert 'logger.exception' in src and 'return empty' in src
    assert 'except Exception' in _read('app', 'customer', 'views_customer_portal.py')


def test_template_tags_balanced():
    s = _read('templates', 'customer_portal', 'shop.html')
    for o, c in (('{% if', '{% endif %}'), ('{% for', '{% endfor %}')):
        assert len(re.findall(re.escape(o) + r'[ \t]', s)) == s.count(c), o

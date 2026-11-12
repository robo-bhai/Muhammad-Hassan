"""Vendor review reply + public rating: wiring check (pure Python; Django ki zaroorat nahi)."""
import ast
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_APP = _ROOT / 'app'
_TPL = _ROOT / 'templates' / 'customer_portal'


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def test_flag_and_catalog():
    src = _read('app', 'module_config', 'shop_flags.py')
    flags = None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'FLAGS':
            flags = ast.literal_eval(node.value)
    default, message = flags['vendor_can_reply_reviews']
    assert default is True and message
    assert "'name': 'vendor_can_reply_reviews'" in _read('app', 'module_config', 'settings_catalog.py')


def test_model_fields_and_migration():
    model = _read('app', 'models', 'trade', 'delivery.py')
    assert 'vendor_reply = models.CharField(max_length=300' in model
    assert 'vendor_replied_at = models.DateTimeField(null=True' in model
    mig = _read('app', 'migrations', '0075_orderreview_vendor_reply.py')
    assert "'0074_store_sponsorship'" in mig
    assert "name='vendor_reply'" in mig and "name='vendor_replied_at'" in mig


def test_routes_and_views():
    urls = _read('app', 'urls.py')
    assert "name='vendor_reviews'" in urls and "name='vendor_reply_review'" in urls
    views = _read('app', 'customer', 'views_reviews.py')
    assert 'def vendor_reviews' in views and 'def vendor_reply_review' in views
    assert "vendor=profile.vendor" in views          # vendor sirf apne store ke review par jawab de
    assert '@require_POST' in views


def test_reply_shown_publicly():
    assert 'rv.reply' in _read('templates', 'customer_portal', 'store_detail.html')
    assert 'review.vendor_reply' in _read('templates', 'customer_portal', 'order_detail.html')
    assert 'vendor_reply_review' in _read('templates', 'customer_portal', 'vendor', 'reviews.html')
    assert 'vendor_reviews' in _read('templates', 'customer_portal', 'vendor', 'dashboard.html')


def test_public_score_on_home_cards():
    assert 'st.rating_avg' in _read('templates', 'customer_portal', 'shop.html')
    assert 'store_rating_map' in _read('app', 'customer', 'views_customer_portal.py')


def test_template_tags_balanced():
    for name in ('vendor/reviews.html', 'store_detail.html', 'order_detail.html', 'vendor/dashboard.html', 'shop.html'):
        s = (_TPL / name).read_text()
        for o, c in (('{% if', '{% endif %}'), ('{% for', '{% endfor %}')):
            assert len(re.findall(re.escape(o) + r'[ \t]', s)) == s.count(c), (name, o)

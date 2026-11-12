"""Vendor deals (Buy 1 Get 1 / Combo / Flash): hisaab ki asal logic + wiring (pure Python; Django ki zaroorat nahi)."""
import ast
import pathlib
import re
import sys
import types
from decimal import Decimal

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def _engine():
    """deals.py ka _apply() bina Django ke chalao (sirf constants + _q + _apply nikal kar)."""
    tree = ast.parse(_read('app', 'customer', 'deals.py'))
    keep = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in ('_q', '_apply'):
            keep.append(n)
        elif isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') in (
                'ZERO', 'CENT', 'MAX_FLASH_PERCENT', 'KIND_ORDER'):
            keep.append(n)
    ns = {'Decimal': Decimal, 'ROUND_HALF_UP': 'ROUND_HALF_UP'}
    from decimal import ROUND_HALF_UP
    ns['ROUND_HALF_UP'] = ROUND_HALF_UP
    exec(compile(ast.Module(keep, []), 'deals_engine', 'exec'), ns)
    return ns['_apply']


class _Item:
    def __init__(self, pid, qty=1):
        self.product_id, self.qty = pid, qty


class _Items:
    def __init__(self, items):
        self._i = items

    def all(self):
        return self._i


class _Deal:
    def __init__(self, pk, kind, items, percent=None, combo_price=None, title='t'):
        self.pk, self.kind, self.percent, self.combo_price, self.title = pk, kind, percent, combo_price, title
        self.items = _Items([_Item(p, q) for p, q in items])


D = Decimal


def test_bogo_cheapest_unit_free():
    apply = _engine()
    r = apply([_Deal(1, 'bogo', [(10, 1)])], {10: [D('100')] * 4})
    assert r['total'] == D('200.00')                 # 4 unit: 2 free
    r = apply([_Deal(1, 'bogo', [(10, 1)])], {10: [D('100')] * 3})
    assert r['total'] == D('100.00')                 # 3 unit: 1 free
    r = apply([_Deal(1, 'bogo', [(10, 1)])], {10: [D('100')]})
    assert r['total'] == D('0.00') and r['lines'] == []   # 1 unit: kuch nahi


def test_combo_sets():
    apply = _engine()
    deal = _Deal(1, 'combo', [(1, 1), (2, 1)], combo_price=D('150'))
    r = apply([deal], {1: [D('100')] * 2, 2: [D('80')] * 3})
    assert r['total'] == D('60.00')                  # 2 set, har set par 180-150=30
    r = apply([deal], {1: [D('100')]})
    assert r['total'] == D('0.00')                   # doosra product nahi: combo nahi
    r = apply([_Deal(1, 'combo', [(1, 1), (2, 1)], combo_price=D('500'))], {1: [D('100')], 2: [D('80')]})
    assert r['total'] == D('0.00')                   # combo mehnga: koi discount nahi


def test_flash_percent_and_one_deal_per_unit():
    apply = _engine()
    r = apply([_Deal(1, 'flash', [(10, 1)], percent=D('20'))], {10: [D('100')] * 2})
    assert r['total'] == D('40.00')
    # BOGO ke baad usi product par flash dobara nahi lagta (4 unit: BOGO ne sab le liye)
    both = [_Deal(1, 'bogo', [(10, 1)]), _Deal(2, 'flash', [(10, 1)], percent=D('50'))]
    r = apply(both, {10: [D('100')] * 4})
    assert r['total'] == D('200.00') and len(r['lines']) == 1
    # 3 unit: BOGO 1 free, bacha 1 unit par flash 50%
    r = apply(both, {10: [D('100')] * 3})
    assert r['total'] == D('150.00')
    # bahut bada percent (90 se zyada) ignore
    r = apply([_Deal(1, 'flash', [(10, 1)], percent=D('95'))], {10: [D('100')]})
    assert r['total'] == D('0.00')


def test_higher_flash_wins_first():
    apply = _engine()
    ds = [_Deal(1, 'flash', [(10, 1)], percent=D('10')), _Deal(2, 'flash', [(10, 1)], percent=D('30'))]
    r = apply(ds, {10: [D('100')]})
    assert r['total'] == D('30.00') and r['lines'][0]['deal'].pk == 2


def test_offers_integration():
    src = _read('app', 'customer', 'offers.py')
    assert 'deals_logic.compute(cart, vendor_id)' in src
    assert "out['discount'] = out['coupon_discount'] + out['deals_discount']" in src
    assert "summary['coupon_discount']" in src          # coupon redemption sirf coupon ka hissa
    assert 'deals_logic.record(order, summary)' in src
    rows = _read('templates', 'customer_portal', '_offer_rows.html')
    assert 'offer.deals' in rows and 'offer.coupon_discount' in rows
    assert 'offer.discount|' not in _read('templates', 'customer_portal', '_offer_box.html')


def test_vendor_bears_the_discount():
    src = _read('app', 'customer', 'vendor_commission.py')
    assert 'vendor_deals_total(vendor)' in src and 'payable -= deals' in src and 'sales -= deals' in src


def test_flag_catalog_urls_migration():
    flags = None
    for n in ast.parse(_read('app', 'module_config', 'shop_flags.py')).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'FLAGS':
            flags = ast.literal_eval(n.value)
    assert flags['vendor_deals_enabled'][0] is True
    assert "'name': 'vendor_deals_enabled'" in _read('app', 'module_config', 'settings_catalog.py')
    urls = _read('app', 'urls.py')
    assert "name='vendor_deals'" in urls and "name='vendor_deal_end'" in urls
    mig = _read('app', 'migrations', '0076_store_deals.py')
    assert "'0075_orderreview_vendor_reply'" in mig
    for m in ('StoreDeal', 'StoreDealItem', 'OrderDeal'):
        assert f"name='{m}'" in mig and f'class {m}(' in _read('app', 'models', 'trade', 'vendor_portal.py')


def test_store_page_shows_deals():
    assert 'deal_badges' in _read('app', 'customer', 'views_stores.py')
    assert 'p.deal_badge' in _read('templates', 'customer_portal', '_store_card.html')
    assert 'store_deals' in _read('templates', 'customer_portal', 'store_detail.html')
    assert 'vendor_deals' in _read('templates', 'customer_portal', 'vendor', 'dashboard.html')


def test_template_tags_balanced():
    for name in ('vendor/deals.html', 'store_detail.html', '_store_card.html', '_offer_rows.html', 'vendor/dashboard.html'):
        s = _read('templates', 'customer_portal', *name.split('/'))
        for o, c in (('{% if', '{% endif %}'), ('{% for', '{% endfor %}')):
            assert len(re.findall(re.escape(o) + r'[ \t]', s)) == s.count(c), (name, o)

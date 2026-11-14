"""Wallet top-up + gift cards: pure helpers aur wiring (Django ki zaroorat nahi)."""
import ast
import pathlib
from decimal import Decimal, InvalidOperation

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def _helpers():
    src = _read('app', 'customer', 'wallet_funds.py')
    tree = ast.parse(src)
    want = {'parse_amount', 'normalize_code', 'format_code'}
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
    ns = {'Decimal': Decimal, 'InvalidOperation': InvalidOperation, 'CENT': Decimal('0.01')}
    exec(compile(ast.Module(fns, []), 'x', 'exec'), ns)
    return ns


def test_parse_amount():
    h = _helpers()
    assert h['parse_amount']('1,500') == Decimal('1500.00')
    assert h['parse_amount'](' 250.5 ') == Decimal('250.50')
    for bad in ('', None, 'abc', '0', '-5'):
        assert h['parse_amount'](bad) is None


def test_code_format_and_normalize():
    h = _helpers()
    assert h['format_code']('7K4MX2QD') == 'GC-7K4M-X2QD'
    assert h['normalize_code'](' gc-7k4m-x2qd ') == 'GC7K4MX2QD'


def test_alphabet_has_no_lookalikes():
    src = _read('app', 'customer', 'wallet_funds.py')
    alpha = next(n.value.value for n in ast.parse(src).body
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'CODE_ALPHABET')
    assert not set('0O1I') & set(alpha)
    assert 'secrets.choice' in src                      # andaza lagane layak nahi (random nahi)


def test_redeem_and_approve_are_race_safe_and_one_time():
    src = _read('app', 'customer', 'wallet_funds.py')
    assert src.count('select_for_update()') >= 3        # approve, reject, redeem teenon lock karte hain
    assert "card.status != 'active'" in src and "req.status != 'pending'" in src
    assert 'MAX_BAD_TRIES' in src and 'cache.set' in src  # galat codes par rok
    assert "reference__iexact=reference" in src          # ek transaction ID do dafa nahi


def test_wiring():
    assert '"trade.wallet_funds"' in _read('app', 'models', '__init__.py')
    flags = _read('app', 'module_config', 'shop_flags.py')
    cat = _read('app', 'module_config', 'settings_catalog.py')
    assert "'shop_gift_cards_enabled'" in flags
    for name in ('shop_gift_cards_enabled', 'wallet_topup_min', 'wallet_topup_max', 'gift_card_valid_days'):
        assert f"'name': '{name}'" in cat, name
    urls = _read('app', 'urls.py')
    for name in ('wallet_topup_request', 'gift_card_buy', 'gift_card_redeem'):
        assert f"name='{name}'" in urls, name
    mig = _read('app', 'migrations', '0083_wallet_funds.py')
    assert "'giftcard'" in mig and 'WalletTopUp' in mig and "('app', '0082_repeat_order_plans')" in mig
    assert "('giftcard', 'Gift card redeem')" in _read('app', 'models', 'trade', 'offers.py')
    admin = _read('app', 'admin', 'vendor_portal.py')
    assert 'class WalletTopUpAdmin' in admin and 'class GiftCardAdmin' in admin
    tpl = _read('templates', 'customer_portal', 'wallet.html')
    for name in ("gift_card_redeem", "wallet_topup_request", "gift_card_buy"):
        assert name in tpl, name

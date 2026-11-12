"""Referral ka flag aur Settings (pure Python; Django ki zaroorat nahi)."""
import ast
import pathlib

_APP = pathlib.Path(__file__).resolve().parents[1] / 'app'
_FLAGS_SRC = (_APP / 'module_config' / 'shop_flags.py').read_text()
_CATALOG_SRC = (_APP / 'module_config' / 'settings_catalog.py').read_text()


def _flags():
    for node in ast.parse(_FLAGS_SRC).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'FLAGS':
            return ast.literal_eval(node.value)
    raise AssertionError('FLAGS not found')


def test_flag_exists_and_is_off_by_default():
    default, message = _flags()['shop_referral_enabled']
    assert default is False
    assert message


def test_settings_are_in_catalog():
    for name in ('shop_referral_enabled', 'referral_reward_referrer', 'referral_reward_referee',
                 'referral_min_order', 'referral_monthly_cap'):
        assert f"'name': '{name}'" in _CATALOG_SRC, name


def test_offers_reads_same_keys():
    src = (_APP / 'customer' / 'offers.py').read_text()
    for name in ('shop_referral_enabled', 'referral_reward_referrer', 'referral_reward_referee',
                 'referral_min_order', 'referral_monthly_cap'):
        assert name in src, name

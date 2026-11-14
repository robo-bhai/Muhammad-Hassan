"""Vendor: loud ringtone + auto-accept (pure wiring checks; Django ki zaroorat nahi)."""
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(*parts):
    return pathlib.Path(_ROOT, *parts).read_text()


def test_auto_accept_hook_is_safe_and_before_reminders():
    src = _read('app', 'customer', 'store_orders.py')
    assert 'def try_auto_accept(order, prof)' in src
    body = src[src.index('def try_auto_accept'):src.index('def _vendor_buttons')]
    assert 'select_for_update()' in body                     # double accept nahi
    assert "locked.status != 'pending'" in body
    assert "apply_vendor_action(locked, 'accept'" in body    # asli accept path (customer notify, WhatsApp, ETA)
    assert 'except Exception' in body and 'return False' in body   # galti par order normal vendor ke paas
    notify = src[src.index('def notify_vendor_new_order'):src.index('def try_auto_accept')]
    assert notify.index('try_auto_accept(order, prof)') < notify.index('_start_reminders')   # auto-accept par reminders nahi


def test_model_migration_and_settings_form():
    model = _read('app', 'models', 'trade', 'vendor_portal.py')
    assert 'auto_accept = models.BooleanField(' in model and 'auto_accept_prep_minutes' in model
    mig = _read('app', 'migrations', '0084_vendor_auto_accept.py')
    assert "('app', '0083_wallet_funds')" in mig and "name='auto_accept'" in mig
    view = _read('app', 'customer', 'views_vendor_portal.py')
    assert "profile.auto_accept, profile.auto_accept_prep_minutes = auto_accept, auto_prep" in view
    assert 'name="auto_accept"' in _read('templates', 'customer_portal', 'vendor', 'store_settings.html')


def test_ringer_loops_until_no_pending_orders():
    orders = _read('templates', 'customer_portal', 'vendor', 'orders.html')
    assert "vendor/_order_ringer.html" in orders
    assert 'beep()' not in orders                              # purani 30 second wali beep hat gayi
    ring = _read('templates', 'customer_portal', 'vendor', '_order_ringer.html')
    assert 'setInterval(function () { if (pending > 0' in ring and 'stopRing' in ring
    assert 'setInterval(poll, 10000)' in ring                  # 30s se 10s
    assert "pointerdown" in ring                               # browser ki awaaz unlock
    assert 'voRingMuted' in ring                               # mute yaad rehta hai

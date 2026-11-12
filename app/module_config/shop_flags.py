# app/module_config/shop_flags.py
"""
Admin-controlled switches for the online shop (Settings > Shop).

One place for: defaults, reading a flag, a view decorator, and a dict for templates.
Values live in SystemSetting (key = flag name), the same table the Settings Center already uses.
To add a new switch: add it to FLAGS here AND as a field in the 'shop' tab of settings_catalog.py.
"""
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

# name -> (default, message shown when the feature is OFF)
FLAGS = {
    'vendor_register_enabled':       (True,  'New seller registration is currently closed.'),
    'vendor_login_enabled':          (True,  'Seller login is currently disabled.'),
    'vendor_auto_approve_accounts':  (None,  ''),   # None = fall back to settings.VENDOR_AUTO_APPROVE_ACCOUNTS
    'vendor_auto_approve_products':  (None,  ''),   # None = fall back to settings.VENDOR_AUTO_APPROVE_PRODUCTS
    'vendor_can_add_products':       (True,  'Adding or editing products is currently disabled for vendors.'),
    'vendor_can_manage_orders':      (True,  'Vendor order management is currently disabled.'),
    'vendor_payout_request_enabled': (True,  'Payout requests are currently disabled. Please contact the admin.'),
    'customer_register_enabled':     (True,  'New customer registration is currently closed.'),
    'customer_login_enabled':        (True,  'Customer login is currently disabled.'),
    'shop_ordering_enabled':         (True,  'Online ordering is paused right now. Please try again later.'),
    'order_tracking_enabled':        (True,  'Order tracking is currently unavailable.'),
    'customer_can_cancel_orders':    (True,  'Cancelling orders online is disabled. Please contact the store.'),
    'customer_can_rate_orders':      (True,  'Order ratings are currently disabled.'),
    'customer_can_dispute_orders':   (True,  'Reporting a problem with an order is currently disabled. Please contact the store.'),
    'shop_stores_enabled':           (True,  'The stores page is currently unavailable.'),
    'shop_banners_enabled':          (True,  ''),
    'shop_distance_fee_enabled':     (False, ''),
    'shop_cuisines_enabled':         (True,  ''),
    'shop_push_enabled':             (True,  'Push notifications are currently unavailable.'),
    'shop_favorites_enabled':        (True,  'Favourites are currently unavailable.'),
    'shop_coupons_enabled':          (True,  'Coupons are currently unavailable.'),
    'shop_wallet_enabled':           (True,  'Wallet is currently unavailable.'),
    'shop_pro_enabled':              (False, 'Pro membership is not available right now.'),
    'shop_loyalty_enabled':          (False, 'Loyalty points are not available right now.'),
    'shop_referral_enabled':         (False, 'The referral program is not available right now.'),
    'shop_search_enabled':           (True,  ''),
    'shop_voice_search_enabled':     (True,  ''),
    'shop_chat_enabled':             (True,  'Chat is currently unavailable.'),
    'rider_login_enabled':           (True,  'Rider login is currently disabled.'),
    'rider_can_accept_orders':       (True,  'Accepting new orders is currently disabled for riders.'),
    'vendor_can_assign_riders':      (True,  'Choosing a rider is currently disabled. Please contact the admin.'),
    'rider_earnings_enabled':        (True,  'The earnings page is currently unavailable.'),
    'rider_register_enabled':        (True,  'New rider registration is currently closed.'),
    'rider_auto_approve':            (False, ''),
}

_SETTINGS_FALLBACK = {
    'vendor_auto_approve_accounts': 'VENDOR_AUTO_APPROVE_ACCOUNTS',
    'vendor_auto_approve_products': 'VENDOR_AUTO_APPROVE_PRODUCTS',
}


def flag_default(name):
    default = FLAGS[name][0]
    if default is None:
        from django.conf import settings
        return bool(getattr(settings, _SETTINGS_FALLBACK.get(name, ''), False))
    return default


def parse_flag(raw, default):
    """'true'/'1'/'yes'/'on' -> True, any other text -> False, None -> default."""
    if raw is None:
        return default
    return str(raw).strip().lower() in ('true', '1', 'yes', 'on')


def shop_flag(name):
    from app.models import SystemSetting
    row = SystemSetting.objects.filter(setting_key=name).values_list('setting_value', flat=True).first()
    return parse_flag(row, flag_default(name))


def shop_flags_all():
    """All flags in ONE query (for templates)."""
    from app.models import SystemSetting
    rows = dict(SystemSetting.objects.filter(setting_key__in=list(FLAGS)).values_list('setting_key', 'setting_value'))
    return {n: parse_flag(rows.get(n), flag_default(n)) for n in FLAGS}


def flag_required(name, json=False, redirect_to='shop_home'):
    """View decorator: when the switch is OFF -> message + back to the shop (or 403 JSON for AJAX)."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if shop_flag(name):
                return view(request, *args, **kwargs)
            text = FLAGS[name][1]
            if json:
                return JsonResponse({'success': False, 'message': text}, status=403)
            messages.info(request, 'ℹ️ ' + text)
            return redirect(redirect_to)
        return wrapper
    return deco

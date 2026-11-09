"""
Step 1: Shop > Vendors switches (admin controlled).

Run from the project root:   python scripts/patches/apply_shop_flags_vendors.py
Safe to run twice (it skips what is already applied). Every anchor is checked; if the code
was changed and an anchor is missing, the script stops and tells you which one.

What it does
  1. app/shop_flags.py              (new)  helper + decorator + defaults
  2. app/settings_catalog.py        new "Shop" tab (6 vendor switches) in Settings Center
  3. app/customer/views_vendor_portal.py   views obey the switches
  4. app/context_processors.py      {{ SHOP.<flag> }} available in templates
  5. templates/customer_portal/base_shop.html   Vendor Login / Become a Vendor links hide when OFF
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()

SHOP_FLAGS_PY = '''# app/shop_flags.py
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
    'vendor_register_enabled':       (True,  'New vendor registration is currently closed.'),
    'vendor_login_enabled':          (True,  'Vendor login is currently disabled.'),
    'vendor_auto_approve_accounts':  (None,  ''),   # None = fall back to settings.VENDOR_AUTO_APPROVE_ACCOUNTS
    'vendor_auto_approve_products':  (None,  ''),   # None = fall back to settings.VENDOR_AUTO_APPROVE_PRODUCTS
    'vendor_can_add_products':       (True,  'Adding or editing products is currently disabled for vendors.'),
    'vendor_can_manage_orders':      (True,  'Vendor order management is currently disabled.'),
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
    from .models import SystemSetting
    row = SystemSetting.objects.filter(setting_key=name).values_list('setting_value', flat=True).first()
    return parse_flag(row, flag_default(name))


def shop_flags_all():
    """All flags in ONE query (for templates)."""
    from .models import SystemSetting
    rows = dict(SystemSetting.objects.filter(setting_key__in=list(FLAGS)).values_list('setting_key', 'setting_value'))
    return {n: parse_flag(rows.get(n), flag_default(n)) for n in FLAGS}


def flag_required(name, json=False):
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
            return redirect('shop_home')
        return wrapper
    return deco
'''

CATALOG_TAB = '''    # --------------------------------------------------------------------- Shop
    {
        'key': 'shop', 'label': 'Shop', 'icon': 'bi-shop',
        'desc': 'Online shop: vendors (register, login, products, orders)',
        'access': 'admin', 'store': 'system',
        'links': [('Vendor approvals', 'vendor_approvals'), ('Shop banners', 'shop_banner_list')],
        'fields': [
            {'name': 'vendor_register_enabled', 'label': 'Become a Vendor (registration)', 'type': 'bool', 'default': True,
             'group': 'Vendors', 'help': 'OFF = the register page and its link are closed. Existing vendors are not affected.'},
            {'name': 'vendor_login_enabled', 'label': 'Vendor Login', 'type': 'bool', 'default': True,
             'group': 'Vendors', 'help': 'OFF = vendors cannot log in (already logged-in sessions stay until they sign out).'},
            {'name': 'vendor_auto_approve_accounts', 'label': 'Auto-approve new vendor accounts', 'type': 'bool',
             'default': bool(getattr(_dj_settings, 'VENDOR_AUTO_APPROVE_ACCOUNTS', False)), 'group': 'Vendors',
             'help': 'OFF = admin approves each vendor (Vendors > Approvals).'},
            {'name': 'vendor_auto_approve_products', 'label': 'Auto-approve vendor products', 'type': 'bool',
             'default': bool(getattr(_dj_settings, 'VENDOR_AUTO_APPROVE_PRODUCTS', False)), 'group': 'Vendors',
             'help': 'OFF = every new or edited product waits for admin approval before it is live.'},
            {'name': 'vendor_can_add_products', 'label': 'Vendors can add / edit products', 'type': 'bool', 'default': True,
             'group': 'Vendors'},
            {'name': 'vendor_can_manage_orders', 'label': 'Vendors can manage orders', 'type': 'bool', 'default': True,
             'group': 'Vendors', 'help': 'OFF = vendors cannot open the orders page or accept / reject / mark ready.'},
        ],
    },
'''


def read(rel):
    p = ROOT / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s  (run this from the project root)' % rel)
    return p, p.read_text(encoding='utf-8')


def once(text, anchor, rel):
    n = text.count(anchor)
    if n != 1:
        sys.exit('ANCHOR PROBLEM in %s (found %d times, need 1):\n%s' % (rel, n, anchor))


def main():
    # 1. helper
    p = ROOT / 'app/shop_flags.py'
    p.write_text(SHOP_FLAGS_PY, encoding='utf-8')
    print('ok  app/shop_flags.py')

    # 2. settings catalog
    rel = 'app/settings_catalog.py'
    p, t = read(rel)
    if "'key': 'shop'" in t:
        print('skip', rel)
    else:
        anchor = '    # -------------------------------------------------------------------- Voice\n'
        once(t, anchor, rel)
        t = t.replace(anchor, CATALOG_TAB + anchor)
        marker = '\nTABS = ['
        once(t, marker, rel)
        t = t.replace(marker, '\nfrom django.conf import settings as _dj_settings\n\nTABS = [', 1)
        p.write_text(t, encoding='utf-8')
        print('ok ', rel)

    # 3. vendor views
    rel = 'app/customer/views_vendor_portal.py'
    p, t = read(rel)
    if 'shop_flags' in t:
        print('skip', rel)
    else:
        a = 'from ..decorators import vendor_login_required\n'
        once(t, a, rel)
        t = t.replace(a, a + 'from ..shop_flags import flag_required, shop_flag\n')
        for old, new in (
            ("return getattr(settings, 'VENDOR_AUTO_APPROVE_ACCOUNTS', False)", "return shop_flag('vendor_auto_approve_accounts')"),
            ("return getattr(settings, 'VENDOR_AUTO_APPROVE_PRODUCTS', False)", "return shop_flag('vendor_auto_approve_products')"),
            ('def vendor_register(request):', "@flag_required('vendor_register_enabled')\ndef vendor_register(request):"),
            ('def vendor_login(request):', "@flag_required('vendor_login_enabled')\ndef vendor_login(request):"),
            ('@vendor_login_required\ndef vendor_product_add(request):',
             "@vendor_login_required\n@flag_required('vendor_can_add_products')\ndef vendor_product_add(request):"),
            ('@vendor_login_required\ndef vendor_product_edit(request, pk):',
             "@vendor_login_required\n@flag_required('vendor_can_add_products')\ndef vendor_product_edit(request, pk):"),
            ('@vendor_login_required\n@require_POST\ndef vendor_create_master(request, kind):',
             "@vendor_login_required\n@flag_required('vendor_can_add_products', json=True)\n@require_POST\ndef vendor_create_master(request, kind):"),
            ('@vendor_login_required\ndef vendor_orders(request):',
             "@vendor_login_required\n@flag_required('vendor_can_manage_orders')\ndef vendor_orders(request):"),
            ('@vendor_login_required\n@require_POST\ndef vendor_order_action(request, pk, action):',
             "@vendor_login_required\n@flag_required('vendor_can_manage_orders')\n@require_POST\ndef vendor_order_action(request, pk, action):"),
            ('@vendor_login_required\ndef vendor_orders_poll(request):',
             "@vendor_login_required\n@flag_required('vendor_can_manage_orders', json=True)\ndef vendor_orders_poll(request):"),
        ):
            once(t, old, rel)
            t = t.replace(old, new)
        p.write_text(t, encoding='utf-8')
        print('ok ', rel)

    # 4. context processor
    rel = 'app/context_processors.py'
    p, t = read(rel)
    if 'shop_flags_all' in t:
        print('skip', rel)
    else:
        a = "        'BUSINESS_MODE': vis['_mode'],\n"
        once(t, a, rel)
        t = t.replace(a, a + "        # Shop switches (Settings > Shop). Lazy: the DB is only hit if a template uses {{ SHOP.xxx }}.\n"
                            "        'SHOP': SimpleLazyObject(shop_flags_all),\n")
        head = 'from django.core.cache import cache\n'
        once(t, head, rel)
        t = t.replace(head, head + 'from django.utils.functional import SimpleLazyObject\n'
                                   'from .shop_flags import shop_flags_all\n', 1)
        p.write_text(t, encoding='utf-8')
        print('ok ', rel)

    # 5. shop template links
    rel = 'templates/customer_portal/base_shop.html'
    p, t = read(rel)
    if 'SHOP.vendor_login_enabled' in t:
        print('skip', rel)
    else:
        for url, flag in (('vendor_login', 'vendor_login_enabled'), ('vendor_register', 'vendor_register_enabled')):
            pat = re.compile(r'([ \t]*)(<a href="\{% url \'' + url + r'\' %\}" class="sidebar-menu-item">.*?</a>)', re.S)
            m = list(pat.finditer(t))
            if len(m) != 1:
                sys.exit('ANCHOR PROBLEM in %s: %s link found %d times' % (rel, url, len(m)))
            m = m[0]
            t = t[:m.start()] + '%s{%% if SHOP.%s %%}\n%s%s\n%s{%% endif %%}' % (
                m.group(1), flag, m.group(1), m.group(2), m.group(1)) + t[m.end():]
        p.write_text(t, encoding='utf-8')
        print('ok ', rel)

    print('\nDone. No migration needed. Restart the server, then open Settings > Shop.')


if __name__ == '__main__':
    main()

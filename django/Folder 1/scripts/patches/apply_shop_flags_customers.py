"""
Step 2: Shop > Customers switches (admin controlled).  Run AFTER apply_shop_flags_vendors.py.

Run from the project root:   python scripts/patches/apply_shop_flags_customers.py
Safe to run twice. Every anchor is checked; if the code changed and an anchor is missing,
the script stops and tells you which one (nothing half-written for that file).

New switches (Settings > Shop > Customers):
  customer_register_enabled   customer sign-up page + links
  customer_login_enabled      customer login page + links
  shop_ordering_enabled       checkout, place order, buy now (cart still works)
  order_tracking_enabled      public "Track Order" page + links
  customer_can_cancel_orders  customer cancel button/endpoint
  customer_can_rate_orders    order rating endpoint
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def read(rel):
    p = ROOT / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s  (run from the project root, after the vendors patch)' % rel)
    return p, p.read_text(encoding='utf-8')


def once(text, anchor, rel):
    n = text.count(anchor)
    if n != 1:
        sys.exit('ANCHOR PROBLEM in %s (found %d times, need 1):\n%s' % (rel, n, anchor))


def add_import(t, rel):
    line = 'from ..shop_flags import flag_required\n'
    if line in t or 'import flag_required' in t:
        return t
    m = re.search(r'^from django\.shortcuts import [^\n(\\]*\n', t, re.M)
    if not m:
        sys.exit('ANCHOR PROBLEM in %s: no single-line "from django.shortcuts import ..." to attach the import to' % rel)
    return t[:m.end()] + line + t[m.end():]


def wrap(t, pattern, flag, rel, count=1):
    """Wrap each match of pattern in {% if SHOP.flag %}...{% endif %} (keeps indentation)."""
    rx = re.compile(r'([ \t]*)(' + pattern + ')', re.S)
    ms = list(rx.finditer(t))
    if len(ms) != count:
        sys.exit('ANCHOR PROBLEM in %s: %r found %d times (expected %d)' % (rel, pattern[:60], len(ms), count))
    for m in reversed(ms):
        ind = m.group(1)
        t = t[:m.start()] + '%s{%% if SHOP.%s %%}\n%s%s\n%s{%% endif %%}' % (ind, flag, ind, m.group(2), ind) + t[m.end():]
    return t


# ---------------------------------------------------------------- 1. shop_flags.py
rel = 'app/shop_flags.py'
p, t = read(rel)
if 'customer_register_enabled' in t:
    print('skip', rel)
else:
    a = "    'vendor_can_manage_orders':      (True,  'Vendor order management is currently disabled.'),\n"
    once(t, a, rel)
    t = t.replace(a, a + """    'customer_register_enabled':     (True,  'New customer registration is currently closed.'),
    'customer_login_enabled':        (True,  'Customer login is currently disabled.'),
    'shop_ordering_enabled':         (True,  'Online ordering is paused right now. Please try again later.'),
    'order_tracking_enabled':        (True,  'Order tracking is currently unavailable.'),
    'customer_can_cancel_orders':    (True,  'Cancelling orders online is disabled. Please contact the store.'),
    'customer_can_rate_orders':      (True,  'Order ratings are currently disabled.'),
""")
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ---------------------------------------------------------------- 2. settings catalog
rel = 'app/settings_catalog.py'
p, t = read(rel)
if 'customer_register_enabled' in t:
    print('skip', rel)
else:
    a = "'help': 'OFF = vendors cannot open the orders page or accept / reject / mark ready.'},\n"
    once(t, a, rel)
    t = t.replace(a, a + """            {'name': 'customer_register_enabled', 'label': 'Customer registration', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = the sign-up page and its links are closed. Existing customers are not affected.'},
            {'name': 'customer_login_enabled', 'label': 'Customer login', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = customers cannot log in (logged-in sessions stay until they sign out).'},
            {'name': 'shop_ordering_enabled', 'label': 'Online ordering (checkout / buy now)', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = browsing and cart still work, but checkout and placing orders are paused.'},
            {'name': 'order_tracking_enabled', 'label': 'Order tracking page', 'type': 'bool', 'default': True,
             'group': 'Customers', 'help': 'OFF = the public Track Order page and its links are closed.'},
            {'name': 'customer_can_cancel_orders', 'label': 'Customers can cancel orders', 'type': 'bool', 'default': True,
             'group': 'Customers'},
            {'name': 'customer_can_rate_orders', 'label': 'Customers can rate orders', 'type': 'bool', 'default': True,
             'group': 'Customers'},
""")
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ---------------------------------------------------------------- 3. views
def patch_views(rel, pairs):
    p, t = read(rel)
    if "flag_required('" in t and pairs[0][1] in t:
        print('skip', rel)
        return
    for old, new in pairs:
        once(t, old, rel)
        t = t.replace(old, new)
    t = add_import(t, rel)
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)


patch_views('app/customer/views_customer_auth.py', [
    ('def customer_register(request):', "@flag_required('customer_register_enabled')\ndef customer_register(request):"),
    ('def customer_login(request):', "@flag_required('customer_login_enabled')\ndef customer_login(request):"),
    ('@customer_login_required\ndef place_order_direct(request):',
     "@flag_required('shop_ordering_enabled')\n@customer_login_required\ndef place_order_direct(request):"),
])

patch_views('app/customer/views_customer_portal.py', [
    ('@customer_login_required\ndef checkout(request):',
     "@flag_required('shop_ordering_enabled')\n@customer_login_required\ndef checkout(request):"),
    ('@transaction.atomic\n@customer_login_required\n@require_POST\ndef place_order(request):',
     "@transaction.atomic\n@flag_required('shop_ordering_enabled')\n@customer_login_required\n@require_POST\ndef place_order(request):"),
    ('def buy_now(request, product_id):',
     "@flag_required('shop_ordering_enabled')\ndef buy_now(request, product_id):"),
    ('def track_order(request):',
     "@flag_required('order_tracking_enabled')\ndef track_order(request):"),
    ('@transaction.atomic\n@customer_login_required\n@require_POST\ndef cancel_order_customer(request, order_id):',
     "@transaction.atomic\n@flag_required('customer_can_cancel_orders')\n@customer_login_required\n@require_POST\ndef cancel_order_customer(request, order_id):"),
])

patch_views('app/customer/views_reviews.py', [
    ('@customer_login_required\n@require_POST\ndef rate_order(request, order_id):',
     "@flag_required('customer_can_rate_orders')\n@customer_login_required\n@require_POST\ndef rate_order(request, order_id):"),
])

patch_views('app/customer/views_order_tracking.py', [
    ('def track_order_public(request):', "@flag_required('order_tracking_enabled')\ndef track_order_public(request):"),
])

# ---------------------------------------------------------------- 4. templates
rel = 'templates/customer_portal/base_shop.html'
p, t = read(rel)
if 'SHOP.order_tracking_enabled' in t:
    print('skip', rel)
else:
    t = wrap(t, r'<a href="\{% url \'track_order\' %\}" class="nav-action-btn.*?</a>', 'order_tracking_enabled', rel)
    t = wrap(t, r'<a href="\{% url \'track_order\' %\}"\s+class="sidebar-menu-item.*?</a>', 'order_tracking_enabled', rel)
    t = wrap(t, r'<a href="\{% url \'customer_login\' %\}"\s+class="sidebar-menu-item.*?</a>', 'customer_login_enabled', rel)
    t = wrap(t, r'<a href="\{% url \'customer_register\' %\}"\s+class="sidebar-menu-item.*?</a>', 'customer_register_enabled', rel)
    t = wrap(t, r'<li><a href="\{% url \'track_order\' %\}">.*?</li>', 'order_tracking_enabled', rel)
    t = wrap(t, r'<li><a href="\{% url \'customer_login\' %\}">.*?</li>', 'customer_login_enabled', rel)
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

for rel, pattern, flag, count in (
    ('templates/customer_portal/auth/login.html', r'<a href="\{% url \'customer_register\' %\}">Register now</a>', 'customer_register_enabled', 1),
    ('templates/customer_portal/auth/register.html', r'<a href="\{% url \'customer_login\' %\}">Login here</a>', 'customer_login_enabled', 1),
    ('templates/customer_portal/shop.html', r'<a href="\{% url \'buy_now\' product.id %\}".*?</a>', 'shop_ordering_enabled', 1),
    ('templates/customer_portal/product_detail.html', r'<a href="\{% url \'buy_now\' product.id %\}".*?</a>', 'shop_ordering_enabled', 1),
    ('templates/customer_portal/cart.html', r'<a href="\{% url \'checkout\' %\}" class="btn btn-checkout.*?</a>', 'shop_ordering_enabled', 2),
):
    p, t = read(rel)
    if 'SHOP.' + flag in t:
        print('skip', rel)
        continue
    p.write_text(wrap(t, pattern, flag, rel, count), encoding='utf-8')
    print('ok ', rel)

print('\nDone. No migration needed. Restart the server, then open Settings > Shop > Customers.')

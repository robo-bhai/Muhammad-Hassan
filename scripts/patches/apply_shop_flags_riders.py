"""
Step 4: Shop > Riders switches (admin controlled).  Run AFTER vendors, customers and pages patches.

Run from the project root:   python scripts/patches/apply_shop_flags_riders.py
Safe to run twice. Every anchor is checked; on a mismatch the script stops and names it.

New switches (Settings > Shop > Riders):
  rider_login_enabled        Rider login page
  rider_can_accept_orders    Riders can accept orders from the offers pool
  vendor_can_assign_riders   Vendors can pick a rider for their order (the form is hidden too)
  rider_earnings_enabled     Rider "Kamai" (earnings) page + its menu link

Also: flag_required() gets an optional redirect_to=... so a blocked action can send the user back
to a sensible page instead of always the shop home.
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def read(rel):
    p = ROOT / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s  (run from the project root, after the earlier shop-flag patches)' % rel)
    return p, p.read_text(encoding='utf-8')


def once(text, anchor, rel):
    n = text.count(anchor)
    if n != 1:
        sys.exit('ANCHOR PROBLEM in %s (found %d times, need 1):\n%s' % (rel, n, anchor))


def wrap(t, pattern, flag, rel, count=1):
    rx = re.compile(r'([ \t]*)(' + pattern + ')', re.S)
    ms = list(rx.finditer(t))
    if len(ms) != count:
        sys.exit('ANCHOR PROBLEM in %s: %r found %d times (expected %d)' % (rel, pattern[:60], len(ms), count))
    for m in reversed(ms):
        ind = m.group(1)
        t = t[:m.start()] + '%s{%% if SHOP.%s %%}\n%s%s\n%s{%% endif %%}' % (ind, flag, ind, m.group(2), ind) + t[m.end():]
    return t


# ------------------------------------------------------------ 1. shop_flags.py
rel = 'app/shop_flags.py'
p, t = read(rel)
if 'rider_login_enabled' in t:
    print('skip', rel)
else:
    a = "    'shop_chat_enabled':             (True,  'Chat is currently unavailable.'),\n"
    once(t, a, rel)
    t = t.replace(a, a + """    'rider_login_enabled':           (True,  'Rider login is currently disabled.'),
    'rider_can_accept_orders':       (True,  'Accepting new orders is currently disabled for riders.'),
    'vendor_can_assign_riders':      (True,  'Choosing a rider is currently disabled. Please contact the admin.'),
    'rider_earnings_enabled':        (True,  'The earnings page is currently unavailable.'),
""")
    if 'redirect_to' not in t:
        for old, new in (
            ('def flag_required(name, json=False):', "def flag_required(name, json=False, redirect_to='shop_home'):"),
            ("            return redirect('shop_home')", "            return redirect(redirect_to)"),
        ):
            once(t, old, rel)
            t = t.replace(old, new)
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ------------------------------------------------------------ 2. settings catalog
rel = 'app/settings_catalog.py'
p, t = read(rel)
if 'rider_login_enabled' in t:
    print('skip', rel)
else:
    a = "'help': 'OFF = the chat endpoints stop answering.'},\n"
    once(t, a, rel)
    t = t.replace(a, a + """            {'name': 'rider_login_enabled', 'label': 'Rider login', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = riders cannot log in (logged-in sessions stay until they sign out).'},
            {'name': 'rider_can_accept_orders', 'label': 'Riders can accept new orders', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = riders cannot take orders from the offers list. Orders given to them directly are not affected.'},
            {'name': 'vendor_can_assign_riders', 'label': 'Vendors can choose a rider', 'type': 'bool', 'default': True,
             'group': 'Riders', 'help': 'OFF = the "Rider do" form is hidden in vendor orders and the action is refused.'},
            {'name': 'rider_earnings_enabled', 'label': 'Rider earnings page', 'type': 'bool', 'default': True,
             'group': 'Riders'},
""")
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ------------------------------------------------------------ 3. rider views
rel = 'app/customer/views_rider_portal.py'
p, t = read(rel)
if "rider_login_enabled" in t:
    print('skip', rel)
else:
    for old, new in (
        ('def rider_login(request):', "@flag_required('rider_login_enabled', redirect_to='shop_home')\ndef rider_login(request):"),
        ('@rider_login_required\n@require_POST\ndef rider_accept_order(request, pk):',
         "@rider_login_required\n@flag_required('rider_can_accept_orders', redirect_to='rider_home')\n@require_POST\ndef rider_accept_order(request, pk):"),
        ('@rider_login_required\ndef rider_earnings(request):',
         "@rider_login_required\n@flag_required('rider_earnings_enabled', redirect_to='rider_home')\ndef rider_earnings(request):"),
        ('@vendor_login_required\n@require_POST\ndef vendor_assign_rider(request, pk):',
         "@vendor_login_required\n@flag_required('vendor_can_assign_riders', redirect_to='vendor_orders')\n@require_POST\ndef vendor_assign_rider(request, pk):"),
    ):
        once(t, old, rel)
        t = t.replace(old, new)
    imp = 'from ..shop_flags import flag_required\n'
    if imp not in t:
        m = re.search(r'^from django\.shortcuts import [^\n(\\]*\n', t, re.M)
        if not m:
            sys.exit('ANCHOR PROBLEM in %s: no single-line "from django.shortcuts import ..."' % rel)
        t = t[:m.end()] + imp + t[m.end():]
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ------------------------------------------------------------ 4. templates
for rel, pattern, flag in (
    ('templates/customer_portal/vendor/orders.html',
     r'<form method="post" action="\{% url \'vendor_assign_rider\' o.id %\}".*?</form>', 'vendor_can_assign_riders'),
    ('templates/customer_portal/rider/base.html',
     r'<a href="\{% url \'rider_earnings\' %\}".*?</a>', 'rider_earnings_enabled'),
):
    p, t = read(rel)
    if re.search(r'\{% if SHOP\.' + flag + r' %\}\s*' + pattern, t, re.S):
        print('skip', rel)
        continue
    p.write_text(wrap(t, pattern, flag, rel), encoding='utf-8')
    print('ok ', rel)

print('\nDone. No migration needed. Restart the server, then open Settings > Shop > Riders.')

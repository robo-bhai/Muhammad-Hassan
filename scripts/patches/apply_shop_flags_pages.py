"""
Step 3: Shop > Shop pages switches (admin controlled).  Run AFTER the vendors and customers patches.

Run from the project root:   python scripts/patches/apply_shop_flags_pages.py
Safe to run twice. Every anchor is checked; on a mismatch the script stops and names it.

New switches (Settings > Shop > Shop pages):
  shop_stores_enabled        Stores list/detail pages, "Stores near you" row, Stores links
  shop_banners_enabled       Admin banners on the shop home and stores page
  shop_search_enabled        Search bars (shop home, sidebar); search text is ignored on the server too
  shop_voice_search_enabled  Microphone button in the search bar
  shop_chat_enabled          Customer chat endpoints (send / read / new / typing / unread / close)
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def read(rel):
    p = ROOT / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s  (run from the project root, after the vendors + customers patches)' % rel)
    return p, p.read_text(encoding='utf-8')


def once(text, anchor, rel):
    n = text.count(anchor)
    if n != 1:
        sys.exit('ANCHOR PROBLEM in %s (found %d times, need 1):\n%s' % (rel, n, anchor))


def ensure_import(t, rel, names):
    """Make sure 'from ..shop_flags import <names>' exists."""
    want = 'from ..shop_flags import %s\n' % names
    if want in t:
        return t
    m = re.search(r'^from \.\.shop_flags import [^\n]*\n', t, re.M)
    if m:
        return t[:m.start()] + want + t[m.end():]
    m = re.search(r'^from django\.shortcuts import [^\n(\\]*\n', t, re.M)
    if not m:
        sys.exit('ANCHOR PROBLEM in %s: no single-line "from django.shortcuts import ..." to attach the import to' % rel)
    return t[:m.end()] + want + t[m.end():]


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
if 'shop_stores_enabled' in t:
    print('skip', rel)
else:
    a = "    'customer_can_rate_orders':      (True,  'Order ratings are currently disabled.'),\n"
    once(t, a, rel)
    t = t.replace(a, a + """    'shop_stores_enabled':           (True,  'The stores page is currently unavailable.'),
    'shop_banners_enabled':          (True,  ''),
    'shop_search_enabled':           (True,  ''),
    'shop_voice_search_enabled':     (True,  ''),
    'shop_chat_enabled':             (True,  'Chat is currently unavailable.'),
""")
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ------------------------------------------------------------ 2. settings catalog
rel = 'app/settings_catalog.py'
p, t = read(rel)
if 'shop_stores_enabled' in t:
    print('skip', rel)
else:
    a = "{'name': 'customer_can_rate_orders', 'label': 'Customers can rate orders', 'type': 'bool', 'default': True,\n             'group': 'Customers'},\n"
    once(t, a, rel)
    t = t.replace(a, a + """            {'name': 'shop_stores_enabled', 'label': 'Stores page', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = stores list/detail pages, the "Stores near you" row and Stores links are closed.'},
            {'name': 'shop_banners_enabled', 'label': 'Banners', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = admin banners are not shown on the shop home or stores page.'},
            {'name': 'shop_search_enabled', 'label': 'Product search', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = search bars are hidden and search text is ignored.'},
            {'name': 'shop_voice_search_enabled', 'label': 'Voice search (microphone)', 'type': 'bool', 'default': True,
             'group': 'Shop pages'},
            {'name': 'shop_chat_enabled', 'label': 'Customer chat', 'type': 'bool', 'default': True,
             'group': 'Shop pages', 'help': 'OFF = the chat endpoints stop answering.'},
""")
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ------------------------------------------------------------ 3. shop views (home, search, banners, chat)
rel = 'app/customer/views_customer_portal.py'
p, t = read(rel)
if "shop_chat_enabled" in t:
    print('skip', rel)
else:
    a = "    search = request.GET.get('search', '').strip()[:100]\n    original_search = search\n"
    once(t, a, rel)
    t = t.replace(a, "    search = request.GET.get('search', '').strip()[:100] if shop_flag('shop_search_enabled') else ''\n    original_search = search\n")
    a = "    context = {\n        'banners': banners,\n        'featured_stores': featured_stores,\n"
    once(t, a, rel)
    t = t.replace(a, "    if not shop_flag('shop_banners_enabled'):\n        banners = []\n"
                     "    if not shop_flag('shop_stores_enabled'):\n        featured_stores = []\n\n" + a)
    rx = re.compile(r'^def (chat_(?:send_message|get_messages|new|typing|unread_count|close))\(request\):', re.M)
    n = len(rx.findall(t))
    if n != 6:
        sys.exit('ANCHOR PROBLEM in %s: expected 6 chat_* views, found %d' % (rel, n))
    t = rx.sub(lambda m: "@flag_required('shop_chat_enabled', json=True)\n" + m.group(0), t)
    t = ensure_import(t, rel, 'flag_required, shop_flag')
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ------------------------------------------------------------ 4. stores views
rel = 'app/customer/views_stores.py'
p, t = read(rel)
if 'shop_stores_enabled' in t:
    print('skip', rel)
else:
    for old, new in (
        ('def store_list(request):', "@flag_required('shop_stores_enabled')\ndef store_list(request):"),
        ('def store_detail(request, pk):', "@flag_required('shop_stores_enabled')\ndef store_detail(request, pk):"),
        ("'banners': banners if show_banners else [],", "'banners': banners if (show_banners and shop_flag('shop_banners_enabled')) else [],"),
    ):
        once(t, old, rel)
        t = t.replace(old, new)
    t = ensure_import(t, rel, 'flag_required, shop_flag')
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

# ------------------------------------------------------------ 5. templates
rel = 'templates/customer_portal/base_shop.html'
p, t = read(rel)
if 'SHOP.shop_stores_enabled' in t:
    print('skip', rel)
else:
    t = wrap(t, r'<a href="\{% url \'store_list\' %\}"\s+class="sidebar-menu-item.*?</a>', 'shop_stores_enabled', rel)
    css = """{% if not SHOP.shop_search_enabled %}<style>.shop-search-section,.sidebar-search-box,.app-search,form#navbarSearchForm{display:none !important}</style>{% endif %}
{% if not SHOP.shop_voice_search_enabled %}<style>.mic-btn,#voiceSearchBtn,.voice-indicator{display:none !important}</style>{% endif %}
"""
    once(t, '</head>', rel)
    t = t.replace('</head>', css + '</head>', 1)
    p.write_text(t, encoding='utf-8')
    print('ok ', rel)

for rel, pattern, count in (
    ('templates/customer_portal/shop.html', r'<a href="\{% url \'store_list\' %\}" class="promo-card promo-c">.*?</a>', 1),
    ('templates/customer_portal/shop.html', r'<a href="\{% url \'store_list\' %\}"><i class="bi bi-shop"></i>Stores</a>', 1),
    ('templates/customer_portal/my_orders.html', r'<a href="\{% url \'store_list\' %\}"><i class="bi bi-shop"></i>Stores</a>', 1),
    ('templates/customer_portal/order_tracking.html', r'<a href="\{% url \'store_list\' %\}"><i class="bi bi-shop"></i>Stores</a>', 1),
    ('templates/customer_portal/account/dashboard.html', r'<a href="\{% url \'store_list\' %\}"><i class="bi bi-shop"></i>Stores</a>', 1),
    ('templates/customer_portal/order_detail.html', r'<a href="\{% url \'store_list\' %\}"><i class="bi bi-shop"></i>Stores</a>', 1),
):
    p, t = read(rel)
    marker = pattern[:40]
    # idempotent: skip if this exact anchor is already wrapped
    already = re.search(r'\{% if SHOP\.shop_stores_enabled %\}\s*' + pattern, t, re.S)
    if already:
        print('skip', rel)
        continue
    p.write_text(wrap(t, pattern, 'shop_stores_enabled', rel, count), encoding='utf-8')
    print('ok ', rel)

print('\nDone. No migration needed. Restart the server, then open Settings > Shop > Shop pages.')

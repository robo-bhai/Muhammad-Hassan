"""Alag-alag PWA har portal ke liye (ERP, Shop, Vendor, Rider, Investor).

Har portal ka apna manifest (naam, rang, icon, scope, id) hai, is liye phone par
alag-alag app install hoti hain. Portal URL se khud pehchana jata hai.
Naya portal: PORTALS mein ek entry + static/pwa/icons/<key>-*.png
"""
from django.http import JsonResponse

# Order matters: pehle specific prefix, aakhir mein default 'erp'.
PORTALS = {
    'rider': {
        'prefixes': ('/shop/rider/',), 'suffix': 'Rider', 'short': 'Rider',
        'start': '/shop/rider/', 'scope': '/shop/rider/', 'theme': '#ff5a00', 'bg': '#fff7f2',
        'desc': 'Delivery rider app - orders, earnings and live location.',
    },
    'vendor': {
        'prefixes': ('/shop/vendor/',), 'suffix': 'Vendor', 'short': 'Vendor',
        'start': '/shop/vendor/', 'scope': '/shop/vendor/', 'theme': '#16a34a', 'bg': '#f3fbf6',
        'desc': 'Vendor portal - products, orders and reports.',
    },
    'shop': {
        'prefixes': ('/shop/',), 'suffix': 'Shop', 'short': 'Shop',
        'start': '/shop/', 'scope': '/shop/', 'theme': '#1e3a8a', 'bg': '#ffffff',
        'desc': 'Order products online with fast delivery.',
    },
    'investor': {
        'prefixes': ('/investor/', '/shareholder/', '/shareholders/portal/'), 'suffix': 'Investor', 'short': 'Investor',
        'start': '/investor/login/', 'scope': '/', 'theme': '#6d28d9', 'bg': '#f7f4fe',
        'desc': 'Shareholder portal - balance, shares and transactions.',
    },
    'erp': {
        'prefixes': (), 'suffix': 'ERP', 'short': 'ERP',
        'start': '/', 'scope': '/', 'theme': '#0d6efd', 'bg': '#ffffff',
        'desc': 'Business management - sales, purchases, stores and reports.',
    },
}


# (css width, css height, device pixel ratio) - iPhone / iPad portrait splash screens
SPLASH = [(440, 956, 3), (402, 874, 3), (430, 932, 3), (393, 852, 3), (428, 926, 3), (390, 844, 3),
          (375, 812, 3), (414, 896, 3), (414, 896, 2), (414, 736, 3), (375, 667, 2),
          (834, 1194, 2), (1024, 1366, 2), (810, 1080, 2), (768, 1024, 2)]


def portal_for_path(path):
    for key, cfg in PORTALS.items():
        if cfg['prefixes'] and path.startswith(cfg['prefixes']):
            return key
    return 'erp'


def _company_name():
    try:
        from app.models import CompanyInfo
        c = CompanyInfo.objects.only('name').first()
        if c and c.name:
            return c.name
    except Exception:
        pass
    return 'Business Management System'


def pwa_manifest(request, portal):
    cfg = PORTALS.get(portal)
    if not cfg:
        from django.http import Http404
        raise Http404
    from app.pwa_icons import icon_url   # logo ho to dynamic, warna static
    icon = lambda n: icon_url(portal, n)
    data = {
        'id': cfg['start'],
        'name': '%s %s' % (_company_name(), cfg['suffix']),
        'short_name': cfg['short'],
        'description': cfg['desc'],
        'start_url': cfg['start'],
        'scope': cfg['scope'],
        'display': 'standalone',
        'orientation': 'any',
        'theme_color': cfg['theme'],
        'background_color': cfg['bg'],
        'lang': 'en-US',
        'dir': 'ltr',
        'icons': [
            {'src': icon('192'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': icon('512'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': icon('maskable-512'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    resp = JsonResponse(data, json_dumps_params={'indent': 2})
    resp['Content-Type'] = 'application/manifest+json'
    resp['Cache-Control'] = 'public, max-age=3600'
    return resp

"""Branded offline page (/offline/): company ka naam + logo, portal ke rang mein.

- Service worker is page ko install par save kar leta hai (internet na ho to yehi dikhta hai).
- Logo seedha page ke andar (data URI) hai, taake offline mein bhi dikhe.
- Portal (shop / rider / vendor / investor / ERP) ka rang aur message page ka JS URL se pehchanta hai.
"""
import base64
import io

from django.core.cache import cache
from django.shortcuts import render
from django.views.decorators.http import require_GET

from app.pwa_portals import PORTALS


def _logo_data_uri(version):
    key = 'pwa_offline_logo_%s' % version
    hit = cache.get(key)
    if hit is not None:
        return hit
    uri = ''
    try:
        from app.pwa_icons import _load_logo
        logo = _load_logo()
        if logo is not None:
            from PIL import Image
            logo.thumbnail((192, 192), Image.LANCZOS)
            buf = io.BytesIO()
            logo.save(buf, 'PNG', optimize=True)
            uri = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        uri = ''
    cache.set(key, uri, 600)
    return uri


@require_GET
def offline_page(request):
    from app.pwa_icons import get_brand
    brand = get_brand()
    logo = _logo_data_uri(brand['version']) if brand['version'] else ''
    portals = {k: {'prefixes': list(c['prefixes']), 'theme': c['theme'], 'bg': c['bg'], 'name': c['suffix']}
               for k, c in PORTALS.items()}
    resp = render(request, 'offline.html', {'brand_name': brand['name'] or 'Business Management System',
                                            'brand_logo': logo, 'portals': portals})
    resp['Cache-Control'] = 'no-cache'
    return resp

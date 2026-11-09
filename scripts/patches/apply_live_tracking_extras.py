"""
Live tracking ke chhote kaam:
  - customer ki delivery location ka pin (checkout par) + map par ghar ka marker
  - rider ke order card par "📍 Pin" navigation button
  - public tracking page par live map (signed token ke saath)
Pehle apply_live_tracking.py aur apply_auto_dispatch.py lagi honi chahiye.
Run from the project root:   python scripts/patches/apply_live_tracking_extras.py
Safe to run twice. Phir:     python manage.py migrate
"""
import sys
from pathlib import Path

root = Path.cwd()


def edit(rel, done, anchor, new=None, after=True):
    p = root / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s (project root se chalayen)' % rel)
    t = p.read_text(encoding='utf-8')
    if done in t:
        print('skip', rel, '(%s)' % done[:30])
        return
    if t.count(anchor) != 1:
        sys.exit('ANCHOR PROBLEM in %s: %d matches for %r (need 1)' % (rel, t.count(anchor), anchor[:60]))
    t = t.replace(anchor, anchor + new if after else new + anchor)
    p.write_text(t, encoding='utf-8')
    print('patched', rel)


if not (root / 'app/customer/dispatch.py').exists():
    sys.exit('Pehle apply_live_tracking.py aur apply_auto_dispatch.py lagayein.')

edit('app/models/trade/sale_orders.py', 'delivery_lat = models',
     '    vendor_responded_at = models.DateTimeField(null=True, blank=True)\n',
     '    delivery_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)\n'
     '    delivery_lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)\n')

edit('app/customer/views_customer_portal.py', 'from . import drop_pin',
     'from . import store_orders\n', 'from . import drop_pin\n')
edit('app/customer/views_customer_portal.py', 'drop_pin.order_fields(request.session)',
     '            **offers.order_fields(summary),\n',
     '            **drop_pin.order_fields(request.session),\n')

edit('app/customer/views_rider_portal.py', "'map_pin'",
     "        'cust_phone': phone, 'wa_cust'",
     "        'map_pin': (f'https://www.google.com/maps/dir/?api=1&destination={o.delivery_lat},{o.delivery_lng}'\n"
     "                    if o.delivery_lat is not None and o.delivery_lng is not None else ''),\n",
     after=False)
edit('templates/customer_portal/rider/home.html', 'r.map_pin',
     '{% if r.map_cust %}',
     '{% if r.map_pin %}<a class="btn l s" style="width:auto" href="{{ r.map_pin }}" target="_blank">📍 Pin</a>{% endif %}',
     after=False)

edit('app/customer/views_order_tracking.py', 'from .views_live_tracking import make_live_token',
     'from ..shop_flags import flag_required\n', 'from .views_live_tracking import make_live_token\n')
edit('app/customer/views_order_tracking.py', "'live_token'",
     "        'search_phone': search_phone,\n",
     "        'live_token': make_live_token(order) if order else None,\n")
edit('templates/customer_portal/track_order_public.html', '_live_map.html',
     '    <!-- Rider Card (if a rider is assigned) -->\n',
     "    {% include 'customer_portal/_live_map.html' %}\n", after=False)

edit('templates/customer_portal/checkout.html', '_drop_pin.html',
     '                <form id="addressForm" onsubmit="return false;">\n',
     "                {% include 'customer_portal/_drop_pin.html' %}\n", after=False)

edit('app/urls.py', 'track_live_public',
     "     path('shop/rider/api/location/', views_live_tracking.rider_location_update, name='rider_location_update'),\n",
     "     path('shop/track/live-public/', views_live_tracking.track_live_public, name='track_live_public'),\n"
     "     path('shop/api/drop-location/', views_live_tracking.customer_set_drop_location, name='customer_set_drop_location'),\n")
print('Done. Ab: python manage.py migrate')

"""
Live rider tracking: models + urls + rider page + customer tracking page.
Run from the project root:   python scripts/patches/apply_live_tracking.py
Safe to run twice. Phir:     python manage.py migrate
"""
import sys
from pathlib import Path

root = Path.cwd()


def edit(rel, marker_done, anchor, new, after=True):
    p = root / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s (project root se chalayen)' % rel)
    t = p.read_text(encoding='utf-8')
    if marker_done in t:
        print('skip', rel)
        return
    if t.count(anchor) != 1:
        sys.exit('ANCHOR PROBLEM in %s: %d matches (need 1)' % (rel, t.count(anchor)))
    t = t.replace(anchor, anchor + new if after else new + anchor)
    p.write_text(t, encoding='utf-8')
    print('patched', rel)


edit('app/models/trade/delivery.py', 'last_location_at',
     "    last_login_at = models.DateTimeField(null=True, blank=True)\n",
     "    last_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)\n"
     "    last_lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)\n"
     "    last_location_at = models.DateTimeField(null=True, blank=True)\n")

edit('app/urls.py', 'views_live_tracking',
     "from app.customer import views_rider_portal\n",
     "from app.customer import views_live_tracking\n")

edit('app/urls.py', 'rider_location_update',
     "     path('shop/rider/api/poll/', views_rider_portal.rider_poll, name='rider_poll'),\n",
     "     path('shop/rider/api/location/', views_live_tracking.rider_location_update, name='rider_location_update'),\n"
     "     path('shop/track/live/<int:order_id>/', views_live_tracking.customer_rider_location, name='customer_rider_location'),\n")

edit('templates/customer_portal/rider/base.html', '_live_location.html',
     "<script>\n(function(){\n  var last = null, audioCtx = null;",
     "{% if rider and rider.is_online and active_count %}{% include 'customer_portal/rider/_live_location.html' %}{% endif %}\n",
     after=False)

edit('templates/customer_portal/order_tracking.html', '_live_map.html',
     "    <!-- Rider Card -->\n",
     "    {% include 'customer_portal/_live_map.html' %}\n",
     after=False)
print('Done. Ab: python manage.py migrate')

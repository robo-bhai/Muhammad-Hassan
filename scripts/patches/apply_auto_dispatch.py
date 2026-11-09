"""
Auto rider dispatch: nazdeek rider ko pehle offer, phir agle ko, phir sab ko.
Pehle apply_live_tracking.py lagana zaroori hai (rider ki location wahin se aati hai).
Run from the project root:   python scripts/patches/apply_auto_dispatch.py
Safe to run twice. Phir:     python manage.py migrate
"""
import sys
from pathlib import Path

root = Path.cwd()


def edit(rel, done, anchor, new=None, after=True, replace_with=None):
    p = root / rel
    if not p.exists():
        sys.exit('MISSING FILE: %s (project root se chalayen)' % rel)
    t = p.read_text(encoding='utf-8')
    if done in t:
        print('skip', rel, '(%s)' % done[:30])
        return
    if t.count(anchor) != 1:
        sys.exit('ANCHOR PROBLEM in %s: %d matches for %r (need 1)' % (rel, t.count(anchor), anchor[:60]))
    if replace_with is not None:
        t = t.replace(anchor, replace_with)
    else:
        t = t.replace(anchor, anchor + new if after else new + anchor)
    p.write_text(t, encoding='utf-8')
    print('patched', rel)


if not (root / 'app/customer/views_live_tracking.py').exists():
    sys.exit('Pehle apply_live_tracking.py lagayein (live tracking patch).')

# ---- models ----
edit('app/models/trade/vendor_portal.py', '    lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)\n    lng =',
     '    delivery_time_max = models.PositiveSmallIntegerField(default=45, help_text="Minutes")\n',
     '    lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)\n'
     '    lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)\n')

p = root / 'app/models/trade/delivery.py'
t = p.read_text(encoding='utf-8')
if 'class DispatchAttempt' not in t:
    t = t.rstrip('\n') + '''


class DispatchAttempt(models.Model):
    """Auto dispatch: kis rider ko kis tarteeb se order offer hua."""
    sale_order = models.OneToOneField('SaleOrder', on_delete=models.CASCADE, related_name='dispatch_attempt')
    ranking = models.JSONField(default=list)     # rider ids, offer ki tarteeb mein
    declined = models.JSONField(default=list)    # riders jinhon ne reject kiya
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "🎯 Dispatch"
'''
    p.write_text(t, encoding='utf-8')
    print('patched app/models/trade/delivery.py')
else:
    print('skip app/models/trade/delivery.py')

# ---- rider views ----
R = 'app/customer/views_rider_portal.py'
edit(R, 'from . import dispatch', 'from . import store_orders\n', 'from . import dispatch\n')
edit(R, "'dist_km'", "        'fee': rider.per_delivery_fee,\n",
     "        'dist_km': dispatch.distance_km(o, rider),\n")
edit(R, 'dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES)]',
     "offers = [_offer_card(o, rider) for o in _offers_qs()] if rider.is_online else []",
     replace_with="offers = [_offer_card(o, rider) for o in dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES)] if rider.is_online else []")
edit(R, 'len(dispatch.visible_orders(',
     "offers = len(list(_offers_qs())) if rider.is_online else 0",
     replace_with="offers = len(dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES)) if rider.is_online else 0")
edit(R, 'dispatch.can_take(order, rider',
     "                raise store_orders.OrderActionError('Ye order ab available nahi.')\n",
     "            if not dispatch.can_take(order, rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES):\n"
     "                raise store_orders.OrderActionError('Ye order abhi kisi aur rider ko offer ho raha hai. Thori der baad dekhein.')\n")

# ---- urls ----
edit('app/urls.py', 'views_dispatch',
     "from app.customer import views_live_tracking\n", "from app.customer import views_dispatch\n")
edit('app/urls.py', 'rider_decline_order',
     "     path('shop/rider/api/location/', views_live_tracking.rider_location_update, name='rider_location_update'),\n",
     "     path('shop/rider/decline/<int:pk>/', views_dispatch.rider_decline_order, name='rider_decline_order'),\n"
     "     path('shop/vendor/api/set-location/', views_dispatch.vendor_set_location, name='vendor_set_location'),\n")

# ---- templates ----
edit('templates/customer_portal/rider/home.html', 'rider_decline_order',
     '        <button class="btn">✅ Accept karein</button></form>\n',
     '      <form method="post" action="{% url \'rider_decline_order\' o.order.id %}" class="acts" style="margin-top:6px">'
     '{% csrf_token %}<button class="btn" style="background:#6b7280">Reject</button></form>\n')
edit('templates/customer_portal/rider/home.html', 'o.dist_km',
     '<small>{{ o.items_count }} item(s)</small>',
     '{% if o.dist_km is not None %}<small>📏 Store se {{ o.dist_km }} km</small>{% endif %}')
edit('templates/customer_portal/vendor/store_settings.html', '_store_location.html',
     '      <form method="post" enctype="multipart/form-data">\n',
     "      {% include 'customer_portal/vendor/_store_location.html' %}\n", after=False)
print('Done. Ab: python manage.py migrate')

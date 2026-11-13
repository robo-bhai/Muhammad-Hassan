"""Web Push: service worker, public key, subscribe / unsubscribe (login wale users: customer, vendor, rider)."""
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .. import push_service
from ..models import PushSubscription

SERVICE_WORKER_JS = r"""
// /shop/ scope ka service worker: offline/static caching + push + badge, sab root /serviceworker.js mein hai.
importScripts('/serviceworker.js');
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
"""

@require_GET
def push_service_worker(request):
    resp = HttpResponse(SERVICE_WORKER_JS, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/shop/'
    resp['Cache-Control'] = 'no-cache'
    return resp


@require_GET
def push_public_key(request):
    ok = push_service.is_configured() and push_service._enabled()
    return JsonResponse({'enabled': bool(ok), 'key': push_service.public_key() if ok else ''})


@require_POST
def push_subscribe(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Login karein.'}, status=401)
    try:
        data = json.loads(request.body or b'{}')
        endpoint = str(data.get('endpoint') or '')
        keys = data.get('keys') or {}
        p256dh, auth = str(keys.get('p256dh') or ''), str(keys.get('auth') or '')
    except (ValueError, AttributeError):
        return JsonResponse({'success': False, 'message': 'Galat data.'}, status=400)
    if not endpoint.startswith('https://') or len(endpoint) > 1000 or not p256dh or not auth \
            or len(p256dh) > 200 or len(auth) > 100:
        return JsonResponse({'success': False, 'message': 'Galat subscription.'}, status=400)

    # Ek browser = ek endpoint: naya login ho to wo browser naye user ka ho jata ha
    PushSubscription.objects.update_or_create(
        endpoint_hash=PushSubscription.hash_endpoint(endpoint),
        defaults={
            'user': request.user, 'endpoint': endpoint, 'p256dh': p256dh, 'auth': auth,
            'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:255],
        },
    )
    return JsonResponse({'success': True})


@require_POST
def push_unsubscribe(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=401)
    try:
        endpoint = str(json.loads(request.body or b'{}').get('endpoint') or '')
    except (ValueError, AttributeError):
        endpoint = ''
    if endpoint:
        PushSubscription.objects.filter(
            user=request.user, endpoint_hash=PushSubscription.hash_endpoint(endpoint)).delete()
    return JsonResponse({'success': True})


# ---- App icon badge (number on the home-screen icon) ------------------------
_PORTALS = ('vendor', 'rider', 'shop', 'investor', 'erp')


def _badge_count(user, portal):
    """Icon par kitni cheezein intezar mein hain (0 = badge hata do). Kabhi exception nahi uthata.
    vendor: naye (pending) orders | rider: offers + assigned (abhi pickup nahi hua)
    shop: chalu orders | investor/erp: unread notifications."""
    if not user.is_authenticated:
        return 0
    try:
        from ..models import DeliveryInfo, Notification, SaleOrder
        if portal not in _PORTALS:    # page ne nahi batayaa: user ke role se andaza
            portal = ('vendor' if getattr(user, 'vendor_profile', None) else
                      'rider' if getattr(user, 'rider_profile', None) else
                      'shop' if getattr(user, 'customer_profile', None) else 'erp')
        if portal == 'vendor':
            vp = getattr(user, 'vendor_profile', None)
            return SaleOrder.objects.filter(vendor=vp.vendor, status='pending').count() if vp else 0
        if portal == 'rider':
            rp = getattr(user, 'rider_profile', None)
            if not rp:
                return 0
            from . import dispatch
            from .views_rider_portal import ACTIVE_STATUSES, MAX_ACTIVE_ORDERS, _offers_qs
            offers = len(dispatch.visible_orders(_offers_qs(), rp, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES)) if rp.is_online else 0
            return offers + DeliveryInfo.objects.filter(rider=rp, status='assigned').count()
        if portal == 'shop':
            cp = getattr(user, 'customer_profile', None)
            if not cp or not getattr(cp, 'customer_id', None):
                return 0
            from .store_orders import OPEN_ORDER_STATUSES
            return SaleOrder.objects.filter(customer_id=cp.customer_id, status__in=OPEN_ORDER_STATUSES).count()
        return Notification.objects.filter(user=user, is_read=False).count()     # investor + erp
    except Exception:
        return 0


@require_GET
def push_badge(request):
    """JSON {count}. Page (pwa_badge.js) aur service worker (push aane par) dono ye poochte hain."""
    portal = (request.GET.get('p') or '').strip().lower()
    resp = JsonResponse({'count': min(_badge_count(request.user, portal), 99)})
    resp['Cache-Control'] = 'no-store'
    return resp

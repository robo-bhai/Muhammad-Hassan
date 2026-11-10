"""Web Push: service worker, public key, subscribe / unsubscribe (login wale users: customer, vendor, rider)."""
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .. import push_service
from ..models import PushSubscription

SERVICE_WORKER_JS = r"""
importScripts('/serviceworker.js');   // offline page + static cache bhi /shop/ par chalay
// Shop push notifications + root service worker ki offline/static caching.
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });

self.addEventListener('push', function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; }
  catch (err) { data = {title: 'Notification', body: event.data ? event.data.text() : ''}; }
  var actions = (data.actions || []).slice(0, 2).map(function (a) { return {action: a.action, title: a.title}; });
  var opts = {
    body: data.body || '',
    icon: data.icon || undefined,              // company logo (portal ke rang mein)
    badge: data.badge || undefined,            // status bar ka chhota monochrome icon
    data: {url: data.url || '/shop/', actions: data.actions || []},
    tag: data.url || undefined,                // same order ka naya status purane ko replace karta hai
    renotify: !!data.url,                      // ... aur phone phir vibrate karta hai
    vibrate: [120, 60, 120],
    timestamp: Date.now()
  };
  if (actions.length) opts.actions = actions;
  event.waitUntil(self.registration.showNotification(data.title || 'Notification', opts));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var d = event.notification.data || {};
  var url = d.url || '/shop/';
  if (event.action) {                          // neeche wala button dabaya gaya
    var list = d.actions || [];
    for (var j = 0; j < list.length; j++) {
      var u = list[j].url || '';
      if (list[j].action === event.action && u.charAt(0) === '/' && u.charAt(1) !== '/' && u.indexOf('\\') === -1) { url = u; break; }
    }
  }
  event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].url.indexOf(url) !== -1 && 'focus' in list[i]) return list[i].focus();
    }
    return self.clients.openWindow(url);
  }));
});
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

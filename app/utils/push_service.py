"""
Web Push bhejne ka kaam (phone/browser par popup, chahe site band ho).

Setup (ek baar):
  1. pip install pywebpush
  2. python manage.py generate_vapid_keys      -> 2 keys print karta hai
  3. Un keys ko settings.py (ya environment) mein rakhein:
        VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CONTACT_EMAIL
Keys ya pywebpush na ho to ye module chupchap kuch nahi karta (order/notification kabhi nahi rukte).
Push sirf HTTPS par (ya localhost par) chalta hai.
"""
import json
import logging
import os
import threading

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def _cfg(name):
    return (getattr(settings, name, None) or os.environ.get(name) or '').strip()


def public_key():
    return _cfg('VAPID_PUBLIC_KEY')


def is_configured():
    if not (_cfg('VAPID_PUBLIC_KEY') and _cfg('VAPID_PRIVATE_KEY')):
        return False
    try:
        import pywebpush  # noqa: F401
    except Exception:
        return False
    return True


def _enabled():
    try:
        from app.shop_flags import shop_flag
        return bool(shop_flag('shop_push_enabled'))
    except Exception:
        return True


def _deliver(subs, payload, urgent=False):
    """Alag thread mein (order/notification ko dheema na kare).
    urgent=True (vendor/rider ka naya order): push service ko 'high' urgency batata hai (doze mode mein bhi jaldi pahunche)
    aur ttl chhota rakhta hai (purana 'naya order' alert baad mein bekaar hota hai)."""
    from django.db import connection
    from django.utils import timezone
    try:
        from pywebpush import WebPushException, webpush
        from app.models import PushSubscription
        private = _cfg('VAPID_PRIVATE_KEY')
        contact = _cfg('VAPID_CONTACT_EMAIL') or 'admin@example.com'
        for s in subs:
            try:
                webpush(
                    subscription_info={'endpoint': s['endpoint'], 'keys': {'p256dh': s['p256dh'], 'auth': s['auth']}},
                    data=payload,
                    vapid_private_key=private,
                    vapid_claims={'sub': f'mailto:{contact}'},   # pywebpush dict badal deta ha, har baar naya
                    ttl=600 if urgent else 3600,
                    headers={'Urgency': 'high'} if urgent else None,
                )
                PushSubscription.objects.filter(pk=s['id']).update(last_success_at=timezone.now())
            except WebPushException as exc:
                code = getattr(getattr(exc, 'response', None), 'status_code', None)
                if code in (404, 410):          # browser ne subscription khatam kar di
                    PushSubscription.objects.filter(pk=s['id']).delete()
                else:
                    logger.warning('Push failed (%s): %s', code, exc)
            except Exception as exc:
                logger.warning('Push error: %s', exc)
    except Exception as exc:
        logger.error('Push delivery error: %s', exc)
    finally:
        try:
            connection.close()
        except Exception:
            pass


# ---- Push ka "profile": kaun sa portal, kitni zaroori, vibration, buttons ----------------------------
# Notification.send(..., link=...) se khud pehchana jata hai (purane call sites badalne ki zaroorat nahi).
# Ya Notification.send(..., push_kind='rider', push_actions=[...]) se zabardasti set karein.
_VIBRATE = {
    'vendor': [400, 150, 400, 150, 400],   # lamba: kitchen/dukaan ke shor mein bhi mehsoos ho
    'rider':  [300, 100, 300, 100, 300],
    'order':  [200, 100, 200],
    'investor': [120],
    'admin':  [150, 80, 150],
}


def _kind_for(url):
    u = url or ''
    if u.startswith('/shop/vendor/'):
        return 'vendor'
    if u.startswith('/shop/rider/'):
        return 'rider'
    if u.startswith(('/investor/', '/shareholder/', '/shareholders/portal/', '/transfers/', '/balance-dividend/')):
        return 'investor'
    if u.startswith('/shop/'):
        return 'order'
    return 'admin'


def _profile(url, kind=None, actions=None):
    """-> dict: kind, urgent, vibrate, interaction, actions (max 2), tag."""
    import time
    u = url or '/shop/'
    kind = kind or _kind_for(u)
    # Naya order alert: vendor ke orders page / rider ke home par bheja jata hai
    urgent = (kind == 'vendor' and u.split('?')[0] == '/shop/vendor/orders/' and '?' not in u) or \
             (kind == 'rider' and u == '/shop/rider/')
    if actions is None:
        if urgent:
            # Accept/Reject jaise buttons ke liye caller signed token wale actions deta hai (push_actions.py);
            # warna sirf "Open".
            actions = [{'action': 'open', 'title': 'Open orders' if kind == 'vendor' else 'Open', 'url': u}]
        elif kind == 'order' and u.startswith(('/shop/order/', '/shop/track/')):
            actions = [{'action': 'open', 'title': 'Track order', 'url': u},
                       {'action': 'orders', 'title': 'My orders', 'url': '/shop/my-orders/'}]
        elif kind in ('investor', 'admin', 'order'):
            actions = [{'action': 'open', 'title': 'Open', 'url': u}]
        else:
            actions = []
    clean = []
    oid = None
    for a in list(actions)[:2]:
        if isinstance(a, dict) and a.get('oid') and oid is None:
            oid = str(a['oid'])[:20]                     # Chrome/Android: sirf 2 buttons
        if isinstance(a, dict) and a.get('action') and a.get('title'):
            item = {'action': str(a['action'])[:30], 'title': str(a['title'])[:30]}
            if a.get('url') and str(a['url']).startswith('/'):   # sirf apni site ke raste
                item['url'] = str(a['url'])[:300]
            if a.get('token'):                                     # seedha action (push_actions.push_action)
                item['token'] = str(a['token'])[:600]
            clean.append(item)
    return {
        'kind': kind,
        'urgent': urgent,
        'vibrate': _VIBRATE.get(kind, [150]),
        'interaction': urgent,                                    # jab tak user dekhe nahi, notification rahe
        'actions': clean,
        # urgent: har order ka apna notification (reminder usi ko replace karta hai, awaaz dobara aati hai)
        'tag': ('%s-order-%s' % (kind, oid)) if (urgent and oid) else
               (('%s-%d' % (kind, int(time.time() * 1000))) if urgent else u),
    }


def send_push(user, title, body='', url=None, kind=None, actions=None):
    """User ke saare registered browsers/phones ko push. Kabhi exception nahi uthata."""
    try:
        if not user or not is_configured() or not _enabled():
            return 0
        from app.models import PushSubscription
        subs = list(PushSubscription.objects.filter(user=user).values('id', 'endpoint', 'p256dh', 'auth'))
        if not subs:
            return 0
        url = url or ('/notifications/' if getattr(user, 'is_staff', False) else '/shop/')   # link na ho to staff ko list
        prof = _profile(url, kind, actions)
        payload = json.dumps({
            'title': str(title)[:120],
            'body': str(body or '')[:300],
            'url': url,
            'kind': prof['kind'],
            'tag': prof['tag'],
            'vibrate': prof['vibrate'],
            'interaction': prof['interaction'],
            'actions': prof['actions'],
        })
        threading.Thread(target=_deliver, args=(subs, payload, prof['urgent']), daemon=True).start()
        return len(subs)
    except Exception as exc:
        logger.error('send_push error: %s', exc)
        return 0


def send_push_after_commit(user, title, body='', url=None, kind=None, actions=None):
    """Transaction mein bana order rollback ho jaye to push na jaye: commit ke baad bhejein."""
    try:
        transaction.on_commit(lambda: send_push(user, title, body, url, kind, actions))
    except Exception as exc:
        logger.error('send_push_after_commit error: %s', exc)

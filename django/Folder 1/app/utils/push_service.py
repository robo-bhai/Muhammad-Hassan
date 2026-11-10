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


def _deliver(subs, payload):
    """Alag thread mein (order/notification ko dheema na kare)."""
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
                    ttl=3600,
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


def send_push(user, title, body='', url=None):
    """User ke saare registered browsers/phones ko push. Kabhi exception nahi uthata."""
    try:
        if not user or not is_configured() or not _enabled():
            return 0
        from app.models import PushSubscription
        subs = list(PushSubscription.objects.filter(user=user).values('id', 'endpoint', 'p256dh', 'auth'))
        if not subs:
            return 0
        payload = json.dumps({
            'title': str(title)[:120],
            'body': str(body or '')[:300],
            'url': url or '/shop/',
        })
        threading.Thread(target=_deliver, args=(subs, payload), daemon=True).start()
        return len(subs)
    except Exception as exc:
        logger.error('send_push error: %s', exc)
        return 0


def send_push_after_commit(user, title, body='', url=None):
    """Transaction mein bana order rollback ho jaye to push na jaye: commit ke baad bhejein."""
    try:
        transaction.on_commit(lambda: send_push(user, title, body, url))
    except Exception as exc:
        logger.error('send_push_after_commit error: %s', exc)

"""Admin ko alert: naya vendor register, naya dispute, waghera.

Active superusers ko in-app notification milti hai (aur Notification.send ki settings ke mutabiq email/push).
Yeh kabhi asli kaam (register / dispute) ko nahi rokta: koi bhi galti sirf log mein jati hai.
"""
import logging

logger = logging.getLogger(__name__)


def alert_admins(title, message, link=None, kind='warning', category='system'):
    """Wapas: kitne admins ko bheja."""
    sent = 0
    try:
        from django.contrib.auth.models import User
        from ..models import Notification
        for user in User.objects.filter(is_superuser=True, is_active=True):
            try:
                Notification.send(user=user, title=title, message=message,
                                  notification_type=kind, category=category, link=link)
                sent += 1
            except Exception:
                logger.exception('admin alert failed for user %s', user.pk)
    except Exception:
        logger.exception('admin alert failed: %s', title)
    return sent

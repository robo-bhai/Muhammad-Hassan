"""Account action history likhne ka helper. Kabhi asli kaam (suspend/approve) ko nahi rokta."""
import logging

logger = logging.getLogger(__name__)


def log_action(kind, ref_id, name, action, reason='', detail='', user=None):
    try:
        from ..models import AccountActionLog
        has_user = bool(getattr(user, 'pk', None))
        return AccountActionLog.objects.create(
            kind=kind, ref_id=ref_id, name=(name or '')[:150], action=action,
            reason=(reason or '')[:255], detail=(detail or '')[:255],
            by=user if has_user else None,
            by_name=(user.get_username() if has_user else '')[:150])
    except Exception:
        logger.exception('account_log: history save failed (%s %s)', action, name)
        return None

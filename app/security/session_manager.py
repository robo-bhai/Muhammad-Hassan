"""
Active sessions: see where an account is signed in, and sign devices out remotely.

* Every login writes a SessionLog row (session key, IP, browser, time) - see
  signals_security.record_successful_login. Logout / timeout / remote sign-out mark
  it inactive. (Rows are written with bulk_create on purpose: the old post_save
  "User Login" announcement on SessionLog is not fired for every login.)
* A row only counts as active while the real Django session still exists, so
  sessions that expired on their own disappear from the list.
* Remote sign-out deletes the Django session on the server, so that device is logged
  out on its next click. Works with the database, cache and file session engines;
  it cannot work with signed-cookie sessions (nothing is stored on the server).
* Session keys are never shown on a page or placed in a URL; rows are addressed by id,
  and a user can only touch their own rows (security admins can touch any).
"""
import logging
from importlib import import_module

from django.conf import settings
from django.utils.timezone import now

logger = logging.getLogger(__name__)


def _store(session_key=None):
    return import_module(settings.SESSION_ENGINE).SessionStore(session_key)


def _session_exists(session_key):
    try:
        return bool(session_key) and _store(session_key).exists(session_key)
    except Exception:
        return True            # cannot verify (e.g. signed-cookie engine): do not hide the row


def register_session(request, user, ip_address, user_agent):
    """Record this login's session. Never raises."""
    from app.models import SessionLog
    try:
        key = request.session.session_key
        if not key:
            request.session.save()
            key = request.session.session_key
        if not key:
            return None
        SessionLog.objects.filter(session_key=key).delete()
        SessionLog.objects.bulk_create([SessionLog(
            user=user, session_key=key, ip_address=ip_address or "0.0.0.0",
            user_agent=(user_agent or "")[:500], is_active=True,
        )])
        return key
    except Exception:
        logger.exception("Could not register session.")
        return None


def close_session(session_key):
    """Mark a session as ended (logout or timeout)."""
    from app.models import SessionLog
    if session_key:
        SessionLog.objects.filter(session_key=session_key, is_active=True).update(
            is_active=False, logout_time=now())


def active_sessions(user=None):
    """Active SessionLog rows (one user, or everyone when user is None), newest first.
    Rows whose Django session is gone are closed on the way."""
    from app.models import SessionLog
    qs = SessionLog.objects.filter(is_active=True).select_related("user")
    if user is not None:
        qs = qs.filter(user=user)
    live = []
    for row in qs.order_by("-last_activity")[:500]:
        if _session_exists(row.session_key):
            live.append(row)
        else:
            close_session(row.session_key)
    return live


def revoke(row):
    """Sign one session out on the server."""
    try:
        _store(row.session_key).delete(row.session_key)
    except Exception:
        logger.exception("Could not delete session from the session store.")
    close_session(row.session_key)


def revoke_all_except(user, keep_session_key):
    """Sign the user out everywhere except the current device. Returns how many."""
    n = 0
    for row in active_sessions(user):
        if row.session_key != keep_session_key:
            revoke(row)
            n += 1
    return n

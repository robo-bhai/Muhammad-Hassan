"""
Per-account lockout (username based) - the second line of defence after the IP block.

The IP block (check_brute_force) stops ONE address. An attacker who spreads guesses
over many IPs against ONE account is stopped here: when an account collects
`threshold` failed logins inside the lockout window - from ANY IP - it is locked
until enough old failures age out. No new database table is needed; the state is
computed from LoginAttempt rows.

    threshold   = max(SecuritySettings.max_login_attempts * 2, 6)
    window      = SecuritySettings.lockout_time (minutes)
    successful login (or an admin unlock) resets the count

Why double the IP limit: a person who mistypes a password a few times is never
locked; only sustained guessing is. The owner gets an email when an account locks,
and can unlock it at Security -> Locked accounts. Requests from a whitelisted IP
(Security -> IP whitelist) are never blocked by this lock, so an attacker cannot
lock the owner out of the office network.

The refusal message is identical for existing and non-existing usernames, so it
cannot be used to find out which usernames are real.
"""
import math
from datetime import timedelta

MIN_THRESHOLD = 6


def lock_threshold(max_login_attempts):
    return max(int(max_login_attempts or 0) * 2, MIN_THRESHOLD)


def minutes_until_unlock(fail_times, threshold, window_minutes, now_dt):
    """Pure rule. `fail_times` = datetimes of failures since the last reset.
    Returns 0 when not locked, else the minutes (>=1) until fewer than `threshold`
    failures remain inside the sliding window."""
    window = timedelta(minutes=window_minutes)
    recent = sorted(t for t in fail_times if t > now_dt - window)
    if len(recent) < threshold:
        return 0
    release = recent[len(recent) - threshold] + window
    return max(1, math.ceil((release - now_dt).total_seconds() / 60))


# ------------------------------------------------------------ database side --
def account_lock_minutes(username):
    """Minutes the account is still locked (0 = free to try)."""
    from django.utils.timezone import now
    from app.models import LoginAttempt, SecuritySettings

    username = (username or "").strip()
    if not username:
        return 0
    policy = SecuritySettings.get_settings()
    current = now()
    since = current - timedelta(minutes=policy.lockout_time)
    last_reset = (LoginAttempt.objects
                  .filter(username__iexact=username, is_success=True, attempted_at__gte=since)
                  .order_by("-attempted_at").values_list("attempted_at", flat=True).first())
    times = list(LoginAttempt.objects
                 .filter(username__iexact=username, is_success=False,
                         attempted_at__gt=last_reset or since)
                 .order_by("attempted_at").values_list("attempted_at", flat=True))
    return minutes_until_unlock(times, lock_threshold(policy.max_login_attempts),
                                policy.lockout_time, current)


def alert_if_just_locked(username, ip_address):
    """Called after every failed login: raise ONE alert (and email) per lock."""
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from django.utils.timezone import now
    from app.models import LoginAttempt, SecuritySettings
    from app.utils.security import create_security_alert

    minutes = account_lock_minutes(username)
    if not minutes:
        return False
    policy = SecuritySettings.get_settings()
    if not cache.add(f"acct_lock_alert:{username.lower()}", 1, policy.lockout_time * 60):
        return False
    since = now() - timedelta(minutes=policy.lockout_time)
    rows = list(LoginAttempt.objects.filter(username__iexact=username, is_success=False,
                                            attempted_at__gte=since)
                .values_list("ip_address", "user_agent"))
    ips = sorted({r[0] for r in rows})[:15]
    agents = sorted({(r[1] or "")[:100] for r in rows if r[1]})[:3]
    User = get_user_model()
    user = User.objects.filter(**{f"{User.USERNAME_FIELD}__iexact": username}).first()
    create_security_alert(
        title=f"Account locked: {username}",
        description=(
            f"Account '{username}' was locked for about {minutes} minutes after {len(rows)} "
            f"failed logins from {len(ips)} IP address(es).\n"
            f"IPs: {', '.join(ips)}\nBrowser / tool: {' | '.join(agents) or '-'}\n"
            f"Unlock at Security -> Locked accounts if this was the real user."
        ),
        alert_type="brute_force", severity="high", user=user, ip_address=ip_address,
    )
    return True


def unlock_account(username, by_user):
    """Admin unlock: writes a reset marker row (the history is kept, nothing is deleted)."""
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from app.models import LoginAttempt

    User = get_user_model()
    user = User.objects.filter(**{f"{User.USERNAME_FIELD}__iexact": username}).first()
    LoginAttempt.objects.create(
        user=user, username=username, ip_address="0.0.0.0", user_agent="",
        is_success=True, failure_reason=f"Unlocked by admin {by_user.get_username()}"[:100],
    )
    cache.delete(f"acct_lock_alert:{username.lower()}")


def list_locked_accounts():
    """[(username, minutes_left, failed_count)] for accounts locked right now."""
    from django.db.models import Count
    from django.utils.timezone import now
    from app.models import LoginAttempt, SecuritySettings

    policy = SecuritySettings.get_settings()
    since = now() - timedelta(minutes=policy.lockout_time)
    rows = (LoginAttempt.objects.filter(is_success=False, attempted_at__gte=since)
            .values("username").annotate(n=Count("id")).filter(n__gte=lock_threshold(policy.max_login_attempts))
            .order_by("-n")[:200])
    out = []
    for r in rows:
        m = account_lock_minutes(r["username"])
        if m:
            out.append((r["username"], m, r["n"]))
    return out

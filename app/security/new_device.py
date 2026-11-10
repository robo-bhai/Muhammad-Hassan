"""
"New device" login alert.

After a successful login, if the user has signed in before but NEVER from this
browser + operating system combination, they get an email ("Was this you?") with
the time, IP and device, and a low-severity entry is written to Security -> Alerts.

* The first login of an account is never flagged (nothing to compare with).
* A device is "known" by browser family + OS (e.g. "Chrome|Windows"), not by the full
  user-agent string, so a normal browser update does not trigger an alert.
* The owner is NOT emailed for every new device of every user (that would be noise);
  only the affected user is. Serious events still go to the owner through
  create_security_alert().
* Switch off with settings.SECURITY_NEW_DEVICE_ALERTS = False.
* Mail errors never break the login.
"""
import logging
import re

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ pure part --
def device_signature(user_agent):
    """'Chrome|Windows'-style signature, or '' when there is no user agent."""
    ua = (user_agent or "").strip()
    if not ua:
        return ""
    if "Edg/" in ua or "EdgA/" in ua or "EdgiOS/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua or "FxiOS/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "Other"
    if re.search(r"iPhone|iPad|iPod", ua):
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os_name = "macOS"
    elif "CrOS" in ua:
        os_name = "ChromeOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Other"
    return f"{browser}|{os_name}"


def is_new_device(prior_user_agents, user_agent):
    """True only if the account has history but none of it matches this device."""
    sig = device_signature(user_agent)
    if not sig:
        return False
    known = {s for s in (device_signature(u) for u in prior_user_agents) if s}
    if not known:
        return False
    return sig not in known


# ------------------------------------------------------------- database part --
def prior_user_agents(user):
    """User agents of earlier successful logins (admin-unlock marker rows excluded)."""
    from app.models import LoginAttempt
    return list(LoginAttempt.objects.filter(user=user, is_success=True)
                .exclude(ip_address="0.0.0.0").values_list("user_agent", flat=True)[:500])


def notify_if_new_device(user, ip_address, user_agent, previous_agents):
    """Email the user and log a low alert. Returns True if flagged. Never raises."""
    try:
        from django.conf import settings
        from django.core.mail import send_mail
        from django.utils.timezone import localtime, now
        from app.models import SecurityAlert

        if not getattr(settings, "SECURITY_NEW_DEVICE_ALERTS", True):
            return False
        if not is_new_device(previous_agents, user_agent):
            return False

        browser, _, os_name = device_signature(user_agent).partition("|")
        when = localtime(now()).strftime("%Y-%m-%d %H:%M")
        SecurityAlert.objects.create(
            title=f"New device login: {user.get_username()}",
            description=f"{user.get_username()} signed in from a new device ({browser} on {os_name}), "
                        f"IP {ip_address}, at {when}.",
            alert_type="suspicious_login", severity="low", user=user, ip_address=ip_address,
        )
        if user.email:
            site = getattr(settings, "SITE_NAME", "ERP System")
            send_mail(
                f"[{site}] New sign-in to your account",
                "\n".join([
                    f"Hello {user.get_username()},", "",
                    "Your account was just used to sign in from a device we have not seen before:", "",
                    f"  Device:  {browser} on {os_name}",
                    f"  IP:      {ip_address}",
                    f"  Time:    {when}", "",
                    "If this was you, no action is needed.",
                    "If it was NOT you, change your password right away and tell your administrator.",
                    "", site,
                ]),
                None, [user.email],
            )
        return True
    except Exception:
        logger.exception("New-device alert failed (login not affected).")
        return False

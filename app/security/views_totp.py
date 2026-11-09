"""Authenticator-app (TOTP) setup, backup codes and disable - for the signed-in user."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.timezone import now

from app.models import CompanyInfo, User2FASettings
from app.utils.security import create_security_alert, get_client_ip

from . import totp

SESSION_PENDING = "totp_pending_secret"


def _company():
    c = CompanyInfo.objects.first()
    return c.name if c else "ERP System"


@login_required
def totp_setup(request):
    """Show the secret / otpauth link, then confirm with a first code."""
    us, _ = User2FASettings.objects.get_or_create(user=request.user)
    enabled = totp.user_has_totp(request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "confirm":
            secret = request.session.get(SESSION_PENDING)
            step = totp.verify_totp(secret, request.POST.get("code")) if secret else None
            if step is None:
                messages.error(request, "The code is wrong. Check the time on your phone and try again.")
                return redirect("totp_setup")
            plain, hashes = totp.new_backup_codes()
            totp.set_totp_secret(us, secret)
            us.backup_codes = hashes
            us.is_2fa_enabled = True
            us.verified_at = now()
            us.save()
            request.session.pop(SESSION_PENDING, None)
            create_security_alert(
                title="Authenticator app enabled",
                description=f"{request.user.username} enabled authenticator-app 2FA",
                alert_type="2fa_failed", severity="low", user=request.user,
                ip_address=get_client_ip(request))
            messages.success(request, "Authenticator app enabled. Save your backup codes now.")
            return render(request, "security/totp_backup_codes.html",
                          {"codes": plain, "company_name": _company()})

        if action == "regenerate" and enabled:
            if not request.user.check_password(request.POST.get("password", "")):
                messages.error(request, "Password is incorrect.")
                return redirect("totp_setup")
            plain, hashes = totp.new_backup_codes()
            us.backup_codes = hashes
            us.save(update_fields=["backup_codes", "updated_at"])
            return render(request, "security/totp_backup_codes.html",
                          {"codes": plain, "company_name": _company()})

        if action == "disable" and enabled:
            if not request.user.check_password(request.POST.get("password", "")):
                messages.error(request, "Password is incorrect.")
                return redirect("totp_setup")
            us.secret_key = ""
            us.backup_codes = []
            us.is_2fa_enabled = False
            us.verified_at = None
            us.save()
            create_security_alert(
                title="Authenticator app disabled",
                description=f"{request.user.username} disabled authenticator-app 2FA",
                alert_type="2fa_failed", severity="medium", user=request.user,
                ip_address=get_client_ip(request))
            messages.success(request, "Authenticator app removed.")
            return redirect("totp_setup")

        return redirect("totp_setup")

    ctx = {"company_name": _company(), "enabled": enabled,
           "backup_left": len(us.backup_codes or [])}
    if not enabled:
        secret = request.session.get(SESSION_PENDING) or totp.generate_secret()
        request.session[SESSION_PENDING] = secret
        ctx.update(secret=secret,
                   uri=totp.provisioning_uri(secret, request.user.get_username(), _company()))
    return render(request, "security/totp_setup.html", ctx)

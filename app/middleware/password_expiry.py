"""
Force a password change when the password is older than the policy allows.

Uses SecuritySettings.password_expiry_days (0 = never expires) and the date of
the newest PasswordHistory row (written by change_password_security). Users who
never changed their password through the system have no history row yet and are
not forced - the clock starts at their first change.

Shareholder and customer accounts are not affected, only staff / superusers.
Place after AuthenticationMiddleware and SecurityMiddleware.
"""
import logging
from datetime import timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.timezone import now

from app.models import PasswordHistory, SecuritySettings

logger = logging.getLogger(__name__)

CHANGE_URL = "/security/change-password/"
EXEMPT = ("/static/", "/media/", "/favicon", "/login/", "/logout/", CHANGE_URL)


class PasswordExpiryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (user is None or not user.is_authenticated
                or not (user.is_staff or user.is_superuser)
                or request.path.startswith(EXEMPT)):
            return self.get_response(request)

        try:
            days = SecuritySettings.get_settings().password_expiry_days
            if days and days > 0:
                last = (PasswordHistory.objects.filter(user=user)
                        .order_by("-created_at").values_list("created_at", flat=True).first())
                if last is not None and last < now() - timedelta(days=days):
                    if (request.path.startswith("/api/")
                            or request.headers.get("x-requested-with") == "XMLHttpRequest"):
                        return JsonResponse({"error": "Password expired"}, status=403)
                    messages.warning(request, "Your password has expired. Please set a new one.")
                    return redirect(CHANGE_URL)
        except Exception:
            logger.exception("Password expiry check failed; request allowed.")
        return self.get_response(request)

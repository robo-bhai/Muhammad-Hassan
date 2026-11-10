"""
Refuse login POSTs for a locked account (see app/security/account_lock.py).

Works for every login form (admin, investor, shop, vendor, rider) because it looks
at the URL (contains "login") and the posted username / email / phone field - no
view needs to change. A locked account gets HTTP 429 even with the CORRECT password.
Place after AuthenticationMiddleware, before the 2FA middleware.
"""
import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render

from app.security.account_lock import account_lock_minutes
from app.utils.security import get_client_ip

logger = logging.getLogger(__name__)

IDENT_FIELDS = ("username", "email", "phone", "mobile", "login", "identifier")
SKIP_PREFIXES = ("/static/", "/media/", "/security/")


class AccountLockoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.method == "POST" and "login" in request.path.lower()
                and not request.path.startswith(SKIP_PREFIXES)):
            minutes = self._locked_minutes(request)
            if minutes:
                if (request.headers.get("x-requested-with") == "XMLHttpRequest"
                        or "application/json" in request.headers.get("accept", "")):
                    resp = JsonResponse({"success": False, "locked": True, "retry_minutes": minutes,
                                         "error": f"Too many failed attempts. Try again in {minutes} minutes."},
                                        status=429)
                else:
                    resp = render(request, "security/account_locked.html", {"minutes": minutes}, status=429)
                resp["Retry-After"] = str(minutes * 60)
                return resp
        return self.get_response(request)

    @staticmethod
    def _locked_minutes(request):
        try:
            ident = next((request.POST[f].strip() for f in IDENT_FIELDS if request.POST.get(f, "").strip()), "")
            if not ident:
                return 0
            from app.models import IPWhitelist
            ip = get_client_ip(request)
            if ip and IPWhitelist.objects.filter(ip_address=ip, is_active=True).exists():
                return 0                                  # office / owner network is never locked out
            names = {ident}
            User = get_user_model()
            user = User.objects.filter(Q(**{f"{User.USERNAME_FIELD}__iexact": ident}) | Q(email__iexact=ident)).first()
            if user:
                names.add(user.get_username())
            return max(account_lock_minutes(n) for n in names)
        except Exception:
            logger.exception("Account lockout check failed; login allowed.")
            return 0

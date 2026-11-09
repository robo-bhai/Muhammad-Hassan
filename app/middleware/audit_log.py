"""
Audit trail: who changed what, from which IP.

Writes one AccessLog row for every state-changing request (POST/PUT/PATCH/
DELETE) by a signed-in user, plus every denied (403) request. Only the field
NAMES of a form are stored - never the values - so passwords, OTPs and card
numbers cannot leak into the log. Paths that look sensitive (password, otp,
security, users, permissions, backup, api-keys, delete) are flagged
is_sensitive=True so they can be filtered in Security -> Logs.

A failure to write the log never breaks the request.
Place after AuthenticationMiddleware.
"""
import logging

from app.models import AccessLog
from app.utils.security import get_client_ip

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_PREFIXES = ("/static/", "/media/", "/favicon", "/api/notifications/",
                 "/api/announce-alerts/", "/testing/run-auto/status/", "/i18n/collect/")
SENSITIVE_WORDS = ("password", "otp", "security", "users", "permission", "backup",
                   "api-key", "delete", "remove", "void", "refund", "restore")
NEVER_FIELDS = {"csrfmiddlewaretoken"}


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._log(request, response)
        except Exception:
            logger.exception("Audit log write failed.")
        return response

    @staticmethod
    def _log(request, response):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or request.path.startswith(SKIP_PREFIXES):
            return
        denied = response.status_code == 403
        if request.method not in WRITE_METHODS and not denied:
            return

        path = request.path
        parts = [p for p in path.split("/") if p]
        module = (parts[0] if parts else "home")[:100]
        sensitive = denied or any(w in path.lower() for w in SENSITIVE_WORDS)
        fields = sorted(k for k in request.POST.keys() if k not in NEVER_FIELDS)[:40] \
            if request.method in WRITE_METHODS else []

        AccessLog.objects.create(
            user=user,
            action=f"{'DENIED ' if denied else ''}{request.method} {path}"[:100],
            module=module,
            details={"status": response.status_code, "path": path[:300], "fields": fields},
            ip_address=get_client_ip(request) or "0.0.0.0",
            user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
            session_id=(request.session.session_key or "")[:100],
            is_sensitive=sensitive,
        )

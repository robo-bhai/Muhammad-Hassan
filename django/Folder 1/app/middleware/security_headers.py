"""
Browser-side hardening headers for every response.

    X-Content-Type-Options   stop MIME sniffing
    Referrer-Policy          do not leak full URLs to other sites
    Permissions-Policy       switch off camera / mic / geolocation unless needed
    Cross-Origin-Opener-Policy
    Strict-Transport-Security (only on HTTPS requests)
    Cache-Control: no-store  for signed-in HTML pages, so a shared computer's
                             Back button cannot show the previous user's data

Headers that a view or another middleware already set are left alone (for
example the frame-ancestors policy from AllowAppFraming).

Optional settings:
    SECURITY_HSTS_SECONDS       default 31536000 (1 year); 0 turns HSTS off
    SECURITY_PERMISSIONS_POLICY default "camera=(self), microphone=(), geolocation=(self), payment=()"
    SECURITY_CSP                full Content-Security-Policy string; unset = not added.
                                Start with SECURITY_CSP_REPORT_ONLY to test safely.
    SECURITY_CSP_REPORT_ONLY    same, but only reports violations in the browser console.

Place it near the top of settings.MIDDLEWARE (after Django's SecurityMiddleware).
"""
from django.conf import settings

_STATIC = ("/static/", "/media/", "/favicon")


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        def put(name, value):
            if value and name not in response:
                response[name] = value

        put("X-Content-Type-Options", "nosniff")
        put("Referrer-Policy", "strict-origin-when-cross-origin")
        put("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
        put("Permissions-Policy", getattr(
            settings, "SECURITY_PERMISSIONS_POLICY",
            "camera=(self), microphone=(), geolocation=(self), payment=()"))

        if request.is_secure():
            seconds = getattr(settings, "SECURITY_HSTS_SECONDS", 31536000)
            if seconds:
                put("Strict-Transport-Security", f"max-age={seconds}; includeSubDomains")

        csp = getattr(settings, "SECURITY_CSP", "")
        if csp and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = csp
        report_only = getattr(settings, "SECURITY_CSP_REPORT_ONLY", "")
        if report_only:
            put("Content-Security-Policy-Report-Only", report_only)

        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated
                and not request.path.startswith(_STATIC)
                and "text/html" in response.get("Content-Type", "")):
            response["Cache-Control"] = "no-store, private"
            response["Pragma"] = "no-cache"

        return response

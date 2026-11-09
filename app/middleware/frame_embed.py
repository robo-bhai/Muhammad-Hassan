from django.conf import settings


class AllowAppFraming:
    """Allow the app to be opened inside an iframe, but only from settings.FRAME_ANCESTORS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Tell Django's XFrameOptionsMiddleware not to add X-Frame-Options: DENY
        response.xframe_options_exempt = True
        ancestors = " ".join(["'self'"] + list(getattr(settings, "FRAME_ANCESTORS", [])))
        response["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
        return response

"""Current request ko thread mein rakhta hai, taa ke cart/fee ka hisab (jahan request nahi pohanchti)
customer ka drop pin aur 'Deliver to' area session se parh sake."""
import threading

_local = threading.local()


def current_request():
    return getattr(_local, 'request', None)


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None

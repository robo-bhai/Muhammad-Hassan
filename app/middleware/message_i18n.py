"""Translates Django flash messages (messages.success / error / ...) into the visitor's language.

It runs just before the template draws the messages, so no view needs changing and f-string
messages ("Order #{no} placed!") are matched by pattern. English visitors are not touched.
"""
from django.contrib.messages import get_messages

from app.i18n.i18n_lang import get_language
from app.i18n.server_t import translate


class MessageTranslationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_template_response(self, request, response):
        try:
            code = get_language(request)['code']
            if code != 'en':
                for m in get_messages(request):
                    if not getattr(m, '_i18n_done', False):
                        m.message = translate(str(m.message), code)
                        m._i18n_done = True
        except Exception:
            pass                                   # never break a page because of a translation
        return response

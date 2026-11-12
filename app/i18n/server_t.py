"""Server-side translation of messages written in Python (flash messages, errors).

Why: the browser translator in components/i18n.html only handles fixed text. Messages that contain
names or numbers ("Order #1234 placed!") never match a dictionary key, so they stayed English.
This module matches them by pattern ("Order #{} placed!") and puts the values back in place.

Use:
    from app.i18n.server_t import tr
    messages.success(request, tr(request, 'Store settings saved.'))      # optional; the middleware
                                                                         # also translates plain messages
Order of lookup: admin-edited dictionary (Translation table)  ->  built-in pattern catalog  ->  original text.
"""
import re

from django.core.cache import cache

from .i18n_lang import get_language
from .portal_messages import CATALOG
try:
    from .portal_messages import TAG_ONLY          # texts used only by the {% t %} template tag
except ImportError:
    TAG_ONLY = []

_PLACEHOLDER = re.compile(r'\{[^{}]*\}')
_TAIL = ' .!?\u06d4\u2026'


def _split(text):
    """'❌ Order not found!' -> ('❌ ', 'Order not found')  (emoji/symbols kept, end punctuation dropped for matching)."""
    t = (text or '').strip()
    m = re.match(r'^([^\w{(\[#"\']*)(.*)$', t, re.S)
    lead, core = (m.group(1), m.group(2)) if m else ('', t)
    return lead, re.sub(r'\s+', ' ', core).rstrip(_TAIL).strip()


def _compile():
    exact, patterns = {}, []
    for en, ur in CATALOG:
        _, core = _split(en)
        n = len(_PLACEHOLDER.findall(core))
        if n == 0:
            exact[core.lower()] = ur
            continue
        parts = _PLACEHOLDER.split(core)
        rx = '^' + '(.+?)'.join(re.escape(p) for p in parts) + '$'
        patterns.append((re.compile(rx, re.S | re.I), ur, len(core)))
    patterns.sort(key=lambda p: -p[2])            # most specific (longest) first
    return exact, patterns


_EXACT, _PATTERNS = _compile()
# every catalog text (also those with {}) keyed by its template form, used by the {% t %} template tag
_TEMPLATES = {_split(en)[1].lower(): ur for en, ur in CATALOG}
_TEMPLATES.update({_split(en)[1].lower(): ur for en, ur in TAG_ONLY})


def _db_exact():
    """Admin-edited Urdu text (Translation Manager) for exact messages; cached for a minute."""
    def load():
        try:
            from ..models import Translation
            return dict(Translation.objects.exclude(ur='').values_list('key', 'ur'))
        except Exception:
            return {}
    return cache.get_or_set('i18n_server_exact', load, 60)


def translate(text, lang='ur'):
    if lang == 'en' or not text or not isinstance(text, str):
        return text
    lead, core = _split(text)
    if not core:
        return text
    key = core.lower()
    if lang == 'ur':
        hit = _db_exact().get(key) or _EXACT.get(key)
        if hit:
            return lead + hit
        for rx, ur, _n in _PATTERNS:
            m = rx.match(core)
            if m:
                try:
                    return lead + ur.format(*m.groups())
                except (IndexError, KeyError, ValueError):
                    return text
    return text


def translate_template(text, lang):
    """Translate a text that still contains {} placeholders (the placeholders are filled afterwards)."""
    if lang != 'ur' or not text:
        return text
    lead, core = _split(text)
    hit = _db_exact().get(core.lower()) or _TEMPLATES.get(core.lower())
    return lead + hit if hit else text


def tr(request, text, **params):
    """Translate `text` for the visitor's language, then fill %-style {name} params if given."""
    code = get_language(request)['code']
    out = translate(text, code)
    return out.format(**params) if params else out

"""{% t "English text with {} placeholders" value1 value2 %}  ->  text in the visitor's language.

Use it for sentences that contain variables, which the browser translator cannot match:

    {% load portal_i18n %}
    {% t "You are a Pro member until {}." active.ends_on|date:"d M Y" %}
    {% t "To see new orders, go <b>Online</b> using the switch above." %}

The text itself may contain simple HTML (<b>, <br>); the values are always HTML-escaped.
Add the Urdu in app/i18n/portal_messages.py (same number of {} in both texts).
"""
from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from app.i18n.server_t import translate_template

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, text, *values):
    lang = context.get('LANG_CODE') or 'en'
    safe = [conditional_escape(v) for v in values]
    tpl = translate_template(text, lang)
    try:
        out = tpl.format(*safe)
    except (IndexError, KeyError, ValueError):
        out = text.format(*safe) if text.count('{}') == len(safe) else text
    return mark_safe(out)

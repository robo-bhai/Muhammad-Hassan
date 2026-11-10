from django import template
from django.utils.html import format_html

from app.pwa_portals import PORTALS, portal_for_path

register = template.Library()


@register.simple_tag(takes_context=True)
def pwa_portal_meta(context):
    """<link rel=manifest> + theme-color + iOS tags for the portal this page belongs to."""
    request = context.get('request')
    key = portal_for_path(request.path) if request is not None else 'erp'
    cfg = PORTALS[key]
    name = cfg['suffix']
    return format_html(
        '<link rel="manifest" href="/pwa/manifest/{k}.json">\n'
        '    <meta name="theme-color" content="{theme}">\n'
        '    <meta name="apple-mobile-web-app-capable" content="yes">\n'
        '    <meta name="apple-mobile-web-app-status-bar-style" content="default">\n'
        '    <meta name="apple-mobile-web-app-title" content="{name}">\n'
        '    <link rel="apple-touch-icon" href="/static/pwa/icons/{k}-apple.png">\n'
        '    <link rel="icon" type="image/png" sizes="192x192" href="/static/pwa/icons/{k}-192.png">',
        k=key, theme=cfg['theme'], name=name)

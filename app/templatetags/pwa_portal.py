from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from app.pwa_portals import PORTALS, portal_for_path

register = template.Library()

# (css width, css height, device pixel ratio) - iPhone / iPad portrait splash screens
SPLASH = [(440, 956, 3), (402, 874, 3), (430, 932, 3), (393, 852, 3), (428, 926, 3), (390, 844, 3),
          (375, 812, 3), (414, 896, 3), (414, 896, 2), (414, 736, 3), (375, 667, 2),
          (834, 1194, 2), (1024, 1366, 2), (810, 1080, 2), (768, 1024, 2)]


def _ios_links(key):
    out = ['<link rel="apple-touch-icon" sizes="120x120" href="/static/pwa/icons/%s-apple-120.png">' % key,
           '<link rel="apple-touch-icon" sizes="152x152" href="/static/pwa/icons/%s-apple-152.png">' % key,
           '<link rel="apple-touch-icon" sizes="167x167" href="/static/pwa/icons/%s-apple-167.png">' % key,
           '<link rel="apple-touch-icon" sizes="180x180" href="/static/pwa/icons/%s-apple.png">' % key]
    for w, h, r in SPLASH:
        out.append('<link rel="apple-touch-startup-image" href="/static/pwa/splash/%s-%dx%d.png" '
                   'media="(device-width: %dpx) and (device-height: %dpx) and (-webkit-device-pixel-ratio: %d) and (orientation: portrait)">'
                   % (key, w * r, h * r, w, h, r))
    return '\n    '.join(out)


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
        '    <link rel="icon" type="image/png" sizes="192x192" href="/static/pwa/icons/{k}-192.png">\n'
        '    {ios}',
        k=key, theme=cfg['theme'], name=name, ios=mark_safe(_ios_links(key)))

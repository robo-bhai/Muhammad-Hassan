from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from app.pwa_icons import icon_url
from app.pwa_portals import PORTALS, SPLASH, portal_for_path

register = template.Library()


def _ios_links(key):
    out = ['<link rel="apple-touch-icon" sizes="120x120" href="%s">' % icon_url(key, 'apple-120'),
           '<link rel="apple-touch-icon" sizes="152x152" href="%s">' % icon_url(key, 'apple-152'),
           '<link rel="apple-touch-icon" sizes="167x167" href="%s">' % icon_url(key, 'apple-167'),
           '<link rel="apple-touch-icon" sizes="180x180" href="%s">' % icon_url(key, 'apple')]
    for w, h, r in SPLASH:
        out.append('<link rel="apple-touch-startup-image" href="%s" '
                   'media="(device-width: %dpx) and (device-height: %dpx) and (-webkit-device-pixel-ratio: %d) and (orientation: portrait)">'
                   % (icon_url(key, 'splash-%dx%d' % (w * r, h * r)), w, h, r))
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
        '    <link rel="icon" type="image/png" sizes="192x192" href="{icon}">\n'
        '    {ios}',
        k=key, theme=cfg['theme'], name=name, icon=icon_url(key, '192'), ios=mark_safe(_ios_links(key)))

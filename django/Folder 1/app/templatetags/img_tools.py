from urllib.parse import quote

from django import template

register = template.Library()
RASTER = ('.jpg', '.jpeg', '.png', '.webp')


@register.filter
def thumb(f, width=480):
    """{{ product.image|thumb:480 }} -> chhoti tasveer ka URL. Local storage na ho to original URL."""
    try:
        if not f:
            return ''
        name = f.name
        if not hasattr(f.storage, 'path') or not name.lower().endswith(RASTER):
            return f.url
        return '/img/%d/%s' % (int(width), quote(name))
    except Exception:
        try:
            return f.url
        except Exception:
            return ''

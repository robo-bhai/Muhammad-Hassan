"""Company logo se har PWA ke icon aur splash screen banata hai.

- Logo CompanyInfo.logo se aata hai (Company Settings mein upload hota hai).
- Har portal ka rang alag rehta hai, is liye phone par apps alag pehchani jati hain.
- Logo na ho ya koi galti ho to purane static PNG par redirect (kuch toot'ta nahi).
- Logo badalne par naya version (?v=...) lagta hai, is liye cache khud refresh hota hai.
"""
import io
import re

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.http import Http404, HttpResponse, HttpResponseRedirect

from app.pwa_portals import PORTALS, SPLASH

BRAND_KEY = 'pwa_brand_v1'
_MEM = {}          # (version, portal, name) -> png bytes
_MEM_MAX = 150

# Icon names -> (pixel size, maskable?)
ICON_SPECS = {
    '192': (192, False),
    '512': (512, False),
    'maskable-512': (512, True),
    'apple-120': (120, False),
    'apple-152': (152, False),
    'apple-167': (167, False),
    'apple': (180, False),
    'badge-96': (96, False),     # push notification ka chhota monochrome icon (safed + transparent)
}
SPLASH_SIZES = {'%dx%d' % (w * r, h * r) for w, h, r in SPLASH}
_SPLASH_RE = re.compile(r'^splash-(\d{3,4})x(\d{3,4})$')


# ---------------------------------------------------------------- brand info
def get_brand():
    """{'version': int, 'name': str} - version 0 ka matlab logo nahi hai."""
    data = cache.get(BRAND_KEY)
    if data is not None:
        return data
    data = {'version': 0, 'name': ''}
    try:
        from app.models import CompanyInfo
        c = CompanyInfo.objects.only('name', 'logo', 'updated_at').first()
        if c:
            data['name'] = c.name or ''
            if c.logo:
                data['version'] = int(c.updated_at.timestamp()) if c.updated_at else 1
    except Exception:
        pass
    cache.set(BRAND_KEY, data, 60)
    return data


def _drop_brand_cache(**kwargs):
    cache.delete(BRAND_KEY)
    _MEM.clear()


def connect_signals():
    post_save.connect(_drop_brand_cache, sender='app.CompanyInfo', dispatch_uid='pwa_brand_save')
    post_delete.connect(_drop_brand_cache, sender='app.CompanyInfo', dispatch_uid='pwa_brand_del')


def static_url(portal, name):
    if name.startswith('splash-'):
        return '/static/pwa/splash/%s-%s.png' % (portal, name[len('splash-'):])
    return '/static/pwa/icons/%s-%s.png' % (portal, name)


def icon_url(portal, name):
    """Logo ho to dynamic URL, warna purana static PNG."""
    v = get_brand()['version']
    if not v:
        return static_url(portal, name)
    return '/pwa/icon/%s/%s.png?v=%d' % (portal, name, v)


# ------------------------------------------------------------------- drawing
def _hex(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _load_logo():
    from PIL import Image
    from app.models import CompanyInfo
    c = CompanyInfo.objects.only('logo').first()
    if not c or not c.logo:
        return None
    with c.logo.open('rb') as fh:
        img = Image.open(fh)
        img.load()
    img = img.convert('RGBA')
    # transparent kinare hata do taake logo bara dikhe
    bbox = img.getchannel('A').getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def _gradient(size_w, size_h, rgb):
    from PIL import Image
    top = tuple(min(255, int(x * 1.12) + 6) for x in rgb)
    bot = tuple(int(x * 0.78) for x in rgb)
    base = Image.new('RGB', (1, size_h))
    px = base.load()
    for y in range(size_h):
        t = y / max(1, size_h - 1)
        px[0, y] = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    return base.resize((size_w, size_h))


def _fit(logo, box_w, box_h):
    from PIL import Image
    r = min(box_w / logo.width, box_h / logo.height)
    return logo.resize((max(1, int(logo.width * r)), max(1, int(logo.height * r))), Image.LANCZOS)


def _font(px):
    from PIL import ImageFont
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
              '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
              'C:/Windows/Fonts/arialbd.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(p, px)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=px)
    except Exception:
        return ImageFont.load_default()


def _draw_icon(logo, rgb, size, maskable):
    from PIL import Image, ImageDraw
    bg = _gradient(size, size, rgb)
    card_ratio = 0.56 if maskable else 0.74           # maskable: safe zone (80% circle)
    card = int(size * card_ratio)
    off = (size - card) // 2
    # white card
    mask = Image.new('L', (size * 2, size * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [off * 2, off * 2, (off + card) * 2, (off + card) * 2], radius=int(card * 0.22) * 2, fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    bg.paste(Image.new('RGB', (size, size), (255, 255, 255)), (0, 0), mask)
    pad = int(card * 0.14)
    fitted = _fit(logo, card - 2 * pad, card - 2 * pad)
    bg.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2), fitted)
    return bg


def _draw_badge(logo, name, size=96):
    """Android status-bar badge: sirf safed shakal + transparency chahiye.
    Logo mein transparency ho to uski shakal; warna company ke pehle harf wala safed gola."""
    from PIL import Image, ImageDraw
    alpha = logo.getchannel('A')
    lo, _hi = alpha.getextrema()
    mask = Image.new('L', (size, size), 0)
    if lo < 200:
        fitted = _fit(alpha, size - 14, size - 14)
        mask.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    else:
        d = ImageDraw.Draw(mask)
        d.ellipse([3, 3, size - 4, size - 4], fill=255)
        letter = (name or 'B').strip()[:1].upper() or 'B'
        font = _font(int(size * 0.58))
        box = d.textbbox((0, 0), letter, font=font)
        d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]),
               letter, fill=0, font=font)
    out = Image.new('RGBA', (size, size), (255, 255, 255, 255))
    out.putalpha(mask)
    return out


def _draw_splash(logo, cfg, name, w, h):
    from PIL import Image, ImageDraw
    rgb = _hex(cfg['theme'])
    img = Image.new('RGB', (w, h), _hex(cfg['bg']))
    box = int(min(w, h) * 0.42)
    fitted = _fit(logo, box, box)
    x, y = (w - fitted.width) // 2, int(h * 0.40) - fitted.height // 2
    img.paste(fitted, (x, y), fitted)
    d = ImageDraw.Draw(img)
    if name:
        font = _font(max(18, int(w * 0.055)))
        text = name if len(name) <= 28 else name[:27] + '…'
        tw = d.textlength(text, font=font)
        d.text(((w - tw) / 2, y + fitted.height + int(h * 0.035)), text, fill=rgb, font=font)
    # neeche chhoti portal-rang ki patti
    bar_w, bar_h = int(w * 0.18), max(4, int(h * 0.004))
    d.rounded_rectangle([(w - bar_w) // 2, int(h * 0.90), (w + bar_w) // 2, int(h * 0.90) + bar_h],
                        radius=bar_h // 2, fill=rgb)
    return img


def render(portal, name):
    """PNG bytes, ya None agar logo nahi hai."""
    cfg = PORTALS[portal]
    brand = get_brand()
    if not brand['version']:
        return None
    key = (brand['version'], portal, name)
    hit = _MEM.get(key)
    if hit:
        return hit
    logo = _load_logo()
    if logo is None:
        return None
    m = _SPLASH_RE.match(name)
    if m:
        img = _draw_splash(logo, cfg, brand['name'], int(m.group(1)), int(m.group(2)))
    elif name == 'badge-96':
        img = _draw_badge(logo, brand['name'], 96)
    else:
        size, maskable = ICON_SPECS[name]
        img = _draw_icon(logo, _hex(cfg['theme']), size, maskable)
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    data = buf.getvalue()
    if len(_MEM) >= _MEM_MAX:
        _MEM.clear()
    _MEM[key] = data
    return data


# ---------------------------------------------------------------------- view
def pwa_icon(request, portal, name):
    if portal not in PORTALS:
        raise Http404
    m = _SPLASH_RE.match(name)
    if m:
        if '%sx%s' % m.groups() not in SPLASH_SIZES:
            raise Http404
    elif name not in ICON_SPECS:
        raise Http404
    try:
        data = render(portal, name)
    except Exception:
        data = None
    if data is None:
        resp = HttpResponseRedirect(static_url(portal, name))
        resp['Cache-Control'] = 'no-cache'
        return resp
    resp = HttpResponse(data, content_type='image/png')
    resp['Cache-Control'] = 'public, max-age=86400'
    return resp

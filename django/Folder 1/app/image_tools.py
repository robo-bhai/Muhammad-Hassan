"""Image compression.

1. /img/<width>/<media path>  : chhoti WebP/JPEG copy banata hai (disk par save, dobara nahi banta).
2. compress_new_uploads       : naya upload hotay hi bari tasveer (max 1600px) chhoti ho jati hai.
Koi bhi galti ho to original tasveer hi chalti hai - kuch nahi tootta.
"""
import hashlib
import io
import os

from django.conf import settings
from django.db.models.signals import pre_save
from django.http import Http404, HttpResponseRedirect
from django.views.static import serve

ALLOWED_WIDTHS = (96, 160, 240, 360, 480, 720, 1080)
RASTER = ('.jpg', '.jpeg', '.png', '.webp')
MAX_SIDE = 1600
SKIP_BELOW = 400 * 1024          # is se chhoti file dobara compress nahi hoti (agar side bhi theek ho)
THUMB_DIR = '_thumbs'


# ---------------------------------------------------------------- thumbnails
def _thumb_root():
    return os.path.join(os.path.realpath(settings.MEDIA_ROOT), THUMB_DIR)


def thumb_view(request, w, path):
    if w not in ALLOWED_WIDTHS:
        raise Http404
    root = os.path.realpath(settings.MEDIA_ROOT)
    src = os.path.realpath(os.path.join(root, path))
    if not src.startswith(root + os.sep) or src.startswith(_thumb_root() + os.sep) or not os.path.isfile(src):
        raise Http404
    ext = os.path.splitext(src)[1].lower()
    original = HttpResponseRedirect(settings.MEDIA_URL + path)
    if ext not in RASTER:
        return original
    webp = 'image/webp' in request.META.get('HTTP_ACCEPT', '')
    out_ext = '.webp' if webp else ('.png' if ext == '.png' else '.jpg')
    try:
        st = os.stat(src)
        key = hashlib.sha1(('%s|%s|%s' % (path, st.st_mtime_ns, st.st_size)).encode()).hexdigest()[:20]
        rel = '%d/%s%s' % (w, key, out_ext)
        dest = os.path.join(_thumb_root(), rel)
        if not os.path.isfile(dest):
            _make_thumb(src, dest, w, out_ext)
        resp = serve(request, rel, document_root=_thumb_root())
    except Exception:
        return original
    resp['Cache-Control'] = 'public, max-age=2592000'
    resp['Vary'] = 'Accept'
    return resp


def _make_thumb(src, dest, w, out_ext):
    from PIL import Image, ImageOps
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((w, 10000), Image.LANCZOS)          # kabhi bara (upscale) nahi karta
        tmp = dest + '.tmp'
        if out_ext == '.webp':
            im.save(tmp, 'WEBP', quality=80, method=4)
        elif out_ext == '.png':
            im.save(tmp, 'PNG', optimize=True)
        else:
            im.convert('RGB').save(tmp, 'JPEG', quality=80, optimize=True, progressive=True)
    os.replace(tmp, dest)


# ------------------------------------------------------------ upload compress
_TARGETS = None


def _targets():
    global _TARGETS
    if _TARGETS is None:
        from django.apps import apps
        _TARGETS = tuple(apps.get_model('app', n) for n in ('Product', 'ShopBanner', 'VendorProfile'))
    return _TARGETS


def _shrink(f):
    """UploadedFile -> (new bytes, new name) ya None agar zaroorat nahi."""
    from PIL import Image, ImageOps
    f.file.seek(0)
    raw = f.file.read()
    f.file.seek(0)
    with Image.open(io.BytesIO(raw)) as im:
        fmt = (im.format or '').upper()
        if fmt not in ('JPEG', 'PNG', 'WEBP'):
            return None
        if max(im.size) <= MAX_SIDE and len(raw) <= SKIP_BELOW:
            return None
        im = ImageOps.exif_transpose(im)
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        base, _ = os.path.splitext(os.path.basename(f.name))
        buf = io.BytesIO()
        has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
        if fmt == 'WEBP':
            im.save(buf, 'WEBP', quality=82, method=4); name = base + '.webp'
        elif fmt == 'PNG' and has_alpha:
            im.save(buf, 'PNG', optimize=True); name = base + '.png'
        else:
            im.convert('RGB').save(buf, 'JPEG', quality=85, optimize=True, progressive=True); name = base + '.jpg'
    data = buf.getvalue()
    if len(data) >= len(raw) and max(Image.open(io.BytesIO(raw)).size) <= MAX_SIDE:
        return None                                       # compress se bari ho gayi - original rakho
    return data, name


def compress_new_uploads(sender, instance, **kwargs):
    if kwargs.get('raw') or not isinstance(instance, _targets()):
        return
    from django.core.files.base import ContentFile
    for field in instance._meta.get_fields():
        if getattr(field, 'get_internal_type', lambda: '')() != 'ImageField':
            continue
        f = getattr(instance, field.name, None)
        if not f or getattr(f, '_committed', True):
            continue                                       # naya upload nahi
        try:
            res = _shrink(f)
            if res:
                f.save(res[1], ContentFile(res[0]), save=False)
        except Exception:
            pass


def connect_signals():
    pre_save.connect(compress_new_uploads, dispatch_uid='compress_new_uploads')

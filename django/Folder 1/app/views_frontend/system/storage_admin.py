"""Admin page: Storage - server par kya kitni jagah le raha hai (superuser only).

- Server disk (kul / use / khali)
- Project ka hisaab: database, uploads, thumbnails, backups, logs, cache, static
- Media ke folder, sab se bari files
- Database ke sab se bare tables
- Safe safai: thumbnails (khud dobara ban jate hain) aur purane logs
Is device ka (browser/PWA) storage page ke JS se dikhta hai.
"""
import heapq
import os
import shutil
from collections import deque
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import connection
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

CACHE_KEY = 'storage_overview_v1'
CACHE_SECONDS = 120
THUMB_DIR = '_thumbs'


def superuser_only(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Access denied! Sirf superuser Storage page dekh sakta hai.')
            return redirect('dashboard')
        return view(request, *args, **kwargs)
    return wrapper


def human(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return ('%d %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024


def walk(path, top=0):
    """(bytes, files, [(size, relpath)] sab se bari top files)"""
    total = files = 0
    heap = []
    if not os.path.isdir(path):
        return 0, 0, []
    for root, _dirs, names in os.walk(path):
        for name in names:
            fp = os.path.join(root, name)
            try:
                size = os.path.getsize(fp)
            except OSError:
                continue
            total += size
            files += 1
            if top:
                item = (size, os.path.relpath(fp, path))
                if len(heap) < top:
                    heapq.heappush(heap, item)
                else:
                    heapq.heappushpop(heap, item)
    return total, files, sorted(heap, reverse=True)


def _db_info():
    db = settings.DATABASES['default']
    engine = db['ENGINE']
    info = {'engine': engine.rsplit('.', 1)[-1], 'size': 0, 'tables': [], 'note': ''}
    try:
        if 'sqlite' in engine:
            base = str(db['NAME'])
            info['size'] = sum(os.path.getsize(base + s) for s in ('', '-wal', '-shm') if os.path.exists(base + s))
            try:                                              # per-table size (agar SQLite mein dbstat ho)
                with connection.cursor() as cur:
                    cur.execute('SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC LIMIT 12')
                    info['tables'] = [(n, s) for n, s in cur.fetchall() if not n.startswith('sqlite_')]
            except Exception:
                info['note'] = 'Table-wise size is SQLite build mein available nahi.'
        elif 'mysql' in engine:
            with connection.cursor() as cur:
                cur.execute('SELECT table_name, data_length + index_length FROM information_schema.tables '
                            'WHERE table_schema = DATABASE() ORDER BY 2 DESC')
                rows = cur.fetchall()
            info['size'] = sum(int(r[1] or 0) for r in rows)
            info['tables'] = [(r[0], int(r[1] or 0)) for r in rows[:12]]
        else:
            info['note'] = 'Is database engine ka size yahan nahi dikhaya jata.'
    except Exception as e:                                    # page kabhi crash na ho
        info['note'] = 'Database size nahi mila: %s' % e
    return info


def _collect():
    base = str(settings.BASE_DIR)
    media = str(settings.MEDIA_ROOT)
    thumbs_path = os.path.join(media, THUMB_DIR)
    local_media = hasattr(default_storage, 'path')

    media_total, media_files, media_top = walk(media, top=20)
    thumb_bytes, thumb_files, _ = walk(thumbs_path)
    uploads_bytes = max(0, media_total - thumb_bytes)

    # media ke upar wale folder (products, company_logo ...)
    folders = []
    if os.path.isdir(media):
        for name in sorted(os.listdir(media)):
            fp = os.path.join(media, name)
            if os.path.isdir(fp) and name != THUMB_DIR:
                b, n, _ = walk(fp)
                folders.append({'name': name, 'bytes': b, 'files': n})
    folders.sort(key=lambda f: -f['bytes'])

    backup_dir = str(getattr(settings, 'BACKUP_DIR', os.path.join(base, 'dbbackup')))
    log_dir = os.path.join(base, 'logs')
    cache_dir = os.path.join(base, 'django_cache')
    static_dir = str(settings.STATIC_ROOT)
    db = _db_info()
    backups_b, backups_n, _ = walk(backup_dir)
    logs_b, logs_n, _ = walk(log_dir)
    cache_b, cache_n, _ = walk(cache_dir)
    static_b, static_n, _ = walk(static_dir)

    parts = [
        {'key': 'db', 'label': 'Database', 'bytes': db['size'], 'files': None, 'color': '#6366f1',
         'hint': db['engine']},
        {'key': 'uploads', 'label': 'Uploads (media)', 'bytes': uploads_bytes, 'files': media_files - thumb_files,
         'color': '#0ea5e9', 'hint': 'Product, logo, banner, documents'},
        {'key': 'thumbs', 'label': 'Thumbnails cache', 'bytes': thumb_bytes, 'files': thumb_files,
         'color': '#14b8a6', 'hint': 'Chhoti tasveerein - khud dobara banti hain', 'clean': 'thumbs'},
        {'key': 'backups', 'label': 'Backups', 'bytes': backups_b, 'files': backups_n, 'color': '#f59e0b',
         'hint': 'Database Backup page se manage karein'},
        {'key': 'logs', 'label': 'Logs', 'bytes': logs_b, 'files': logs_n, 'color': '#ef4444',
         'hint': 'Debug / backup logs', 'clean': 'logs'},
        {'key': 'cache', 'label': 'App cache', 'bytes': cache_b, 'files': cache_n, 'color': '#a855f7',
         'hint': 'Django cache (khud saaf hota rehta hai)'},
        {'key': 'static', 'label': 'Static files', 'bytes': static_b, 'files': static_n, 'color': '#64748b',
         'hint': 'CSS / JS (collectstatic)'},
    ]
    project_total = sum(p['bytes'] for p in parts)
    for p in parts:
        p['pct'] = round(p['bytes'] * 100.0 / project_total, 1) if project_total else 0
        p['human'] = human(p['bytes'])

    try:
        du = shutil.disk_usage(base)
        disk = {'total': du.total, 'used': du.used, 'free': du.free,
                'pct': round(du.used * 100.0 / du.total, 1) if du.total else 0}
    except Exception:
        disk = None

    return {
        'generated': timezone.now().isoformat(timespec='seconds'),
        'disk': disk,
        'parts': parts,
        'project_total': project_total,
        'local_media': local_media,
        'media_files': media_files,
        'folders': folders,
        'top_files': [{'size': s, 'path': p.replace(os.sep, '/')} for s, p in media_top],
        'db': db,
        'paths': {'media': media, 'backups': backup_dir},
    }


def _decorate(data):
    """human-readable strings (cache mein sirf numbers rakhte hain)."""
    d = dict(data)
    if d.get('disk'):
        d['disk'] = dict(d['disk'], total_h=human(d['disk']['total']), used_h=human(d['disk']['used']),
                         free_h=human(d['disk']['free']))
    d['project_total_h'] = human(d['project_total'])
    d['folders'] = [dict(f, human=human(f['bytes']),
                         pct=round(f['bytes'] * 100.0 / max(1, sum(x['bytes'] for x in d['folders'])), 1))
                    for f in d['folders']]
    d['top_files'] = [dict(f, human=human(f['size'])) for f in d['top_files']]
    d['db'] = dict(d['db'], size_h=human(d['db']['size']),
                   tables=[{'name': n, 'human': human(s), 'bytes': s} for n, s in d['db']['tables']])
    return d


@superuser_only
def storage_overview(request):
    data = None if request.GET.get('refresh') else cache.get(CACHE_KEY)
    if data is None:
        data = _collect()
        cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return render(request, 'settings/storage.html', {'s': _decorate(data)})


@superuser_only
@require_POST
def storage_clean(request):
    action = request.POST.get('action')
    media = str(settings.MEDIA_ROOT)
    freed = 0
    if action == 'thumbs':
        path = os.path.join(media, THUMB_DIR)
        freed, _, _ = walk(path)
        shutil.rmtree(path, ignore_errors=True)
        messages.success(request, 'Thumbnails saaf: %s khali hue. Tasveerein jab dobara khulengi khud ban jayengi.' % human(freed))
    elif action == 'logs':
        log_dir = os.path.join(str(settings.BASE_DIR), 'logs')
        if os.path.isdir(log_dir):
            for name in os.listdir(log_dir):
                fp = os.path.join(log_dir, name)
                if not os.path.isfile(fp):
                    continue
                try:
                    size = os.path.getsize(fp)
                    if name.endswith('.log'):                 # chalu log: aakhri 500 lines rakho
                        with open(fp, 'r', encoding='utf-8', errors='replace') as fh:
                            tail = deque(fh, maxlen=500)
                        with open(fp, 'w', encoding='utf-8') as fh:
                            fh.writelines(tail)
                        freed += max(0, size - os.path.getsize(fp))
                    elif '.log.' in name:                     # purane rotate shuda logs
                        os.remove(fp)
                        freed += size
                except OSError:
                    continue
        messages.success(request, 'Logs saaf: %s khali hue (har log ki aakhri 500 lines rakhi gayi).' % human(freed))
    else:
        messages.error(request, 'Ghalat action.')
    cache.delete(CACHE_KEY)
    return redirect('storage_overview')

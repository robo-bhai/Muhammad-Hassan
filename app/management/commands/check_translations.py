"""Find text in the customer / vendor / rider portal templates that has no Urdu yet.

    python manage.py check_translations             # summary + list of missing text
    python manage.py check_translations --roman     # only text that looks like Roman Urdu (should be English)
    python manage.py check_translations --strict    # exit code 1 when anything is missing (for CI)
"""
import os
import re
from html.parser import HTMLParser

from django.conf import settings
from django.core.management.base import BaseCommand

from app.i18n import i18n_service as svc

ROMAN = re.compile(r'\b(aap|apna|apni|apne|nahi|karein|karen|chunein|abhi|dobara|likhein|jaise|baad|hain|mein|'
                   r'dein|lein|hai|ho|gaya|gayi|zyada|kam az kam|raabta|rabta|tayyar|maal|masla|jawab)\b', re.I)


class _P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        for k, v in attrs:
            if k in ('placeholder', 'title', 'aria-label') and v:
                self.out.append(v)

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def _strings(path):
    t = open(path, encoding='utf-8', errors='ignore').read()
    t = re.sub(r'\{#.*?#\}', '', t, flags=re.S)
    t = re.sub(r'\{%.*?%\}|\{\{.*?\}\}', ' | ', t, flags=re.S)
    p = _P()
    p.feed(t)
    for chunk in p.out:
        for part in chunk.split('|'):
            c = svc.clean_source(part)
            if len(c) >= 3 and re.search(r'[A-Za-z]{2}', c) and not re.search(r'[\u0600-\u06FF]', c):
                yield c


class Command(BaseCommand):
    help = 'List portal text that is missing an Urdu translation, or is written in Roman Urdu.'

    def add_arguments(self, parser):
        parser.add_argument('--roman', action='store_true', help='show only Roman-Urdu looking text')
        parser.add_argument('--strict', action='store_true', help='exit with code 1 if anything is missing')
        parser.add_argument('--portal', choices=['customer', 'vendor', 'rider', 'all'], default='all')

    def handle(self, *args, **o):
        from app.models import Translation
        svc.ensure_seeded()
        have = set(Translation.objects.exclude(ur='').values_list('key', flat=True))
        base = os.path.join(settings.BASE_DIR, 'templates', 'customer_portal')
        total_missing = 0
        for root, _d, files in os.walk(base):
            rel = os.path.relpath(root, base)
            portal = 'vendor' if rel.startswith('vendor') else 'rider' if rel.startswith('rider') else 'customer'
            if o['portal'] not in ('all', portal):
                continue
            for f in sorted(x for x in files if x.endswith('.html')):
                miss = sorted({s for s in _strings(os.path.join(root, f))
                               if svc.make_key(s) not in have and (not o['roman'] or ROMAN.search(s))})
                if miss:
                    total_missing += len(miss)
                    self.stdout.write(self.style.WARNING('%s/%s  (%d)' % (portal, os.path.join(rel, f).lstrip('./'), len(miss))))
                    for s in miss[:30]:
                        self.stdout.write('    - ' + s[:110])
        self.stdout.write(self.style.SUCCESS('Done. Missing: %d' % total_missing) if not total_missing
                          else self.style.ERROR('Missing: %d' % total_missing))
        if o['strict'] and total_missing:
            raise SystemExit(1)

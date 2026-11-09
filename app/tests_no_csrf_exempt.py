"""
Guard: app ke kisi view par csrf_exempt wapas na aa jaye.

Run:  python manage.py test app.tests_no_csrf_exempt
"""
import pathlib

from django.test import SimpleTestCase

import app.views as old_views

APP_DIR = pathlib.Path(__file__).resolve().parent


class NoCsrfExemptTests(SimpleTestCase):
    def test_dead_pos_views_are_gone(self):
        for name in ('pos_quick_add', 'pos_complete_sale', 'pos_hold_sale'):
            self.assertFalse(hasattr(old_views, name), name)

    def test_no_csrf_exempt_in_app_code(self):
        offenders = []
        for path in APP_DIR.rglob('*.py'):
            rel = path.relative_to(APP_DIR).as_posix()
            if rel.startswith(('migrations/', '_backups/')) or path.name.startswith('tests_'):
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            if 'csrf_exempt' in text:
                offenders.append(rel)
        self.assertEqual(offenders, [], 'csrf_exempt mila: %s' % offenders)

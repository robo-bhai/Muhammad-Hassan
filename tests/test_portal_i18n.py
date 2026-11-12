"""Portal language tests: message catalog is consistent and the translator behaves."""
import re
import unittest

from app.i18n.portal_messages import CATALOG
from app.i18n.server_t import translate

PH = re.compile(r'\{[^{}]*\}')


class CatalogTests(unittest.TestCase):
    def test_placeholders_match(self):
        for en, ur in CATALOG:
            self.assertEqual(len(PH.findall(en)), len(PH.findall(ur)), en)

    def test_no_duplicates(self):
        keys = [en.lower() for en, _ in CATALOG]
        self.assertEqual(len(keys), len(set(keys)))

    def test_urdu_is_urdu(self):
        for en, ur in CATALOG:
            self.assertTrue(re.search(r'[\u0600-\u06FF]', ur), en)


class TranslateTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(translate('Cart is empty!', 'ur'), 'کارٹ خالی ہے!')

    def test_emoji_prefix_kept(self):
        self.assertTrue(translate('❌ Phone or password is incorrect', 'ur').startswith('❌ '))

    def test_dynamic_values(self):
        out = translate('Order #ORD-7 placed!', 'ur')
        self.assertIn('ORD-7', out)
        self.assertNotIn('placed', out)

    def test_english_untouched(self):
        self.assertEqual(translate('Cart is empty!', 'en'), 'Cart is empty!')

    def test_unknown_text_unchanged(self):
        self.assertEqual(translate('Something brand new', 'ur'), 'Something brand new')


class TemplateTagTextTests(unittest.TestCase):
    """Texts used by {% t %} in templates: placeholder counts must match the Urdu."""

    def test_template_lookup_keeps_placeholders(self):
        from app.i18n.server_t import translate_template
        out = translate_template('Valid for {} days', 'ur')
        self.assertIn('{}', out)
        self.assertEqual(out.format(30), '30 دن تک چلتا ہے')

    def test_template_lookup_english_unchanged(self):
        from app.i18n.server_t import translate_template
        self.assertEqual(translate_template('Valid for {} days', 'en'), 'Valid for {} days')

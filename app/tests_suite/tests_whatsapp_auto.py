"""
Tests: WhatsApp automatic updates (app/customer/whatsapp_auto.py).

Run:  python manage.py test app.tests_suite.tests_whatsapp_auto -v 2

NOTE: written by reading the code, without a Django project to run it in. Network (requests) and
settings are patched, so no WhatsApp account is needed.
"""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from app.customer import whatsapp_auto as wa

ORDER = SimpleNamespace(order_no='A12', prep_minutes=20, reject_reason='Maal khatam', vendor_id=1, pk=1,
                        customer=SimpleNamespace(contact_number='0300 1234567'))
RIDER = SimpleNamespace(name='Ali', phone='03111111111')


class PhoneTests(SimpleTestCase):
    def test_normalize(self):
        self.assertEqual(wa.normalize_phone('0300 1234567'), '923001234567')
        self.assertEqual(wa.normalize_phone('+92-300-1234567'), '923001234567')
        self.assertEqual(wa.normalize_phone('3001234567'), '923001234567')
        self.assertEqual(wa.normalize_phone('0092 300 1234567'), '923001234567')
        self.assertIsNone(wa.normalize_phone(''))
        self.assertIsNone(wa.normalize_phone('12'))

    def test_lang_code(self):
        self.assertEqual(wa._lang_code('en_us'), 'en_US')
        self.assertEqual(wa._lang_code('EN'), 'en')
        self.assertEqual(wa._lang_code(''), 'en')

    def test_template_text_has_no_newlines(self):
        self.assertEqual(wa._template_text('a\n\nb   c\t d'), 'a b c d')


class TextTests(SimpleTestCase):
    def test_customer_messages(self):
        self.assertIn('#A12', wa.customer_text(ORDER, 'placed', 'Ali Store'))
        self.assertIn('20 minute', wa.customer_text(ORDER, 'accept', 'Ali Store'))
        self.assertIn('Ali (03111111111)', wa.customer_text(ORDER, 'pickup', 'Ali Store', RIDER))
        self.assertIn('deliver ho gaya', wa.customer_text(ORDER, 'delivered', 'Ali Store'))
        self.assertIn('Maal khatam', wa.customer_text(ORDER, 'reject', 'Ali Store'))

    def test_vendor_messages(self):
        self.assertIn('Naya order #A12', wa.vendor_text(ORDER, 'placed', 'S'))
        self.assertEqual(wa.vendor_text(ORDER, 'accept', 'S'), '')      # accept par vendor ko kuch nahi


class SendTests(SimpleTestCase):
    ENV = {'WHATSAPP_CLOUD_TOKEN': 't', 'WHATSAPP_PHONE_NUMBER_ID': '999'}

    def _post(self, status=200):
        return mock.patch('requests.post', return_value=SimpleNamespace(status_code=status, text='x'))

    def test_no_credentials(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            ok, detail = wa.send_message('0300 1234567', 'hi')
        self.assertFalse(ok)

    def test_plain_text_when_no_template(self):
        with mock.patch.dict('os.environ', self.ENV, clear=True), \
                mock.patch.object(wa, '_setting_text', return_value=''), self._post() as post:
            ok, _ = wa.send_message('0300 1234567', 'hi')
        self.assertTrue(ok)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['type'], 'text')
        self.assertEqual(payload['to'], '923001234567')
        self.assertIn('/999/messages', post.call_args.args[0])

    def test_template_payload(self):
        vals = {'whatsapp_template_name': 'order_update', 'whatsapp_template_lang': 'en_us'}
        with mock.patch.dict('os.environ', self.ENV, clear=True), \
                mock.patch.object(wa, '_setting_text', side_effect=lambda k, d='': vals.get(k, d)), \
                self._post() as post:
            ok, _ = wa.send_message('0300 1234567', 'line1\nline2')
        self.assertTrue(ok)
        tpl = post.call_args.kwargs['json']['template']
        self.assertEqual(tpl['name'], 'order_update')
        self.assertEqual(tpl['language']['code'], 'en_US')
        self.assertEqual(tpl['components'][0]['parameters'][0]['text'], 'line1 line2')

    def test_http_error_returns_false(self):
        with mock.patch.dict('os.environ', self.ENV, clear=True), \
                mock.patch.object(wa, '_setting_text', return_value=''), self._post(status=400):
            ok, detail = wa.send_message('0300 1234567', 'hi')
        self.assertFalse(ok)
        self.assertIn('400', detail)


class NotifyTests(SimpleTestCase):
    def test_disabled_sends_nothing(self):
        with mock.patch.object(wa, 'is_enabled', return_value=False), \
                mock.patch.object(wa.threading, 'Thread') as th:
            wa.notify(ORDER, 'placed')
        th.assert_not_called()

    def test_never_raises(self):
        with mock.patch.object(wa, 'is_enabled', side_effect=RuntimeError('db down')):
            wa.notify(ORDER, 'placed')       # exception bahar nahi aani chahiye

    def test_unknown_event_ignored(self):
        with mock.patch.object(wa, 'is_enabled', return_value=True), \
                mock.patch.object(wa.threading, 'Thread') as th:
            wa.notify(ORDER, 'nonsense')
        th.assert_not_called()

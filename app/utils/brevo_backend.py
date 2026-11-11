"""Django email backend: Brevo (ex-Sendinblue) HTTP API.

settings.py is backend ko tab chunta hai jab BREVO_API_KEY aur BREVO_SENDER_EMAIL maujood hon
(GitHub Secrets -> workflow env). Sirf standard library, koi naya package nahi.

Zaroori: BREVO_SENDER_EMAIL Brevo mein *verified sender* ho (Brevo -> Senders, Domains & Dedicated IPs),
warna Brevo mail reject kar deta hai.
"""
import base64
import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

API_URL = 'https://api.brevo.com/v3/smtp/email'
TIMEOUT = 15


class BrevoAPIEmailBackend(BaseEmailBackend):

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or []:
            try:
                if self._send(message):
                    sent += 1
            except Exception as exc:
                logger.error('Brevo send failed: %s', exc)
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, message):
        api_key = getattr(settings, 'BREVO_API_KEY', '')
        sender_email = getattr(settings, 'BREVO_SENDER_EMAIL', '')
        if not (api_key and sender_email):
            raise RuntimeError('BREVO_API_KEY / BREVO_SENDER_EMAIL set nahi hain')
        recipients = list(message.to or [])
        if not recipients:
            return False

        # Display name: message ke from_email se, warna BREVO_SENDER_NAME. Address hamesha verified sender ka.
        name = parseaddr(message.from_email or '')[0] or getattr(settings, 'BREVO_SENDER_NAME', '') or 'Store'

        html = None
        for content, mimetype in getattr(message, 'alternatives', []) or []:
            if mimetype == 'text/html':
                html = content
        if html is None and getattr(message, 'content_subtype', '') == 'html':
            html = message.body

        payload = {
            'sender': {'name': name, 'email': sender_email},
            'to': [{'email': r} for r in recipients],
            'subject': message.subject or '(no subject)',
        }
        if html:
            payload['htmlContent'] = html
            if message.body and message.content_subtype != 'html':
                payload['textContent'] = message.body
        else:
            payload['textContent'] = message.body or ' '
        if message.cc:
            payload['cc'] = [{'email': r} for r in message.cc]
        if message.bcc:
            payload['bcc'] = [{'email': r} for r in message.bcc]
        if message.reply_to:
            payload['replyTo'] = {'email': message.reply_to[0]}

        attachments = []
        for att in getattr(message, 'attachments', []) or []:
            if isinstance(att, tuple) and len(att) >= 2:
                filename, content = att[0], att[1]
                if isinstance(content, str):
                    content = content.encode('utf-8')
                attachments.append({'name': filename, 'content': base64.b64encode(content).decode('ascii')})
        if attachments:
            payload['attachment'] = attachments

        req = urllib.request.Request(
            API_URL, data=json.dumps(payload).encode('utf-8'), method='POST',
            headers={'api-key': api_key, 'content-type': 'application/json', 'accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode('utf-8')[:300]
            except Exception:
                detail = ''
            raise RuntimeError(f'Brevo HTTP {exc.code}: {detail}')

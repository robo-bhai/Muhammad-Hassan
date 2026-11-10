"""
Field-level encryption (Talabat jaisa: "most critical data is stored in encrypted form").

Database mein address / CNIC jaise fields Fernet (AES-128-CBC + HMAC) se encrypt hote hain.
Django code ko farq nahi parta: model se parhte waqt khud decrypt, save karte waqt khud encrypt.

KEY
  settings.DATA_ENCRYPTION_KEY ya environment variable DATA_ENCRYPTION_KEY.
  Key generate karne ke liye:
      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  Key rotation: "nayi_key,purani_key" (comma se). Pehli key se encrypt hota hai, sab se decrypt.
  Agar key set nahi to SECRET_KEY se key banti hai (chal jata hai, lekin SECRET_KEY badli to data parha
  nahi jaye ga). Production mein alag DATA_ENCRYPTION_KEY zaroor rakhein, aur uska backup alag jagah rakhein.

HADOOD (zaroor parhein)
  * Encryption random hai, is liye in fields par exact lookup / icontains / order_by kaam NAHI karta.
    Sirf wahi fields encrypt karein jin par search ya login lookup nahi hota (phone par nahi lagaya).
  * Khali value ('' ya None) encrypt nahi hoti, to filter(field='') / exclude(field='') chalte hain.
  * Purana plaintext data parha jata hai (prefix na ho to jyon ka tyon). `manage.py encrypt_existing_data`
    purane rows ko encrypt kar deta hai.
"""
import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django import forms
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

PREFIX = 'enc1:'
_fernet_cache = {}
_warned = []


class _Undecryptable(str):
    """Decrypt na ho saka (galat key). Page crash nahi hota, aur save par asal ciphertext wapas jata hai."""
    def __new__(cls, ciphertext):
        obj = super().__new__(cls, '[encrypted]')
        obj.ciphertext = ciphertext
        return obj


def _keys():
    raw = getattr(settings, 'DATA_ENCRYPTION_KEY', None) or os.environ.get('DATA_ENCRYPTION_KEY', '')
    keys = [k.strip() for k in str(raw).split(',') if k.strip()]
    if keys:
        return keys
    if not _warned:
        _warned.append(1)
        logger.warning('DATA_ENCRYPTION_KEY set nahi: SECRET_KEY se key bana rahe hain. Production mein alag key rakhein.')
    digest = hashlib.sha256(('data-encryption:' + settings.SECRET_KEY).encode()).digest()
    return [base64.urlsafe_b64encode(digest).decode()]


def _fernet():
    keys = tuple(_keys())
    f = _fernet_cache.get(keys)
    if f is None:
        f = MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])
        _fernet_cache.clear()
        _fernet_cache[keys] = f
    return f


def encrypt_value(value):
    if value is None or value == '':
        return value
    if isinstance(value, _Undecryptable):
        return value.ciphertext
    value = str(value)
    if value.startswith(PREFIX):          # pehle se encrypted
        return value
    return PREFIX + _fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt_value(value):
    if value is None or value == '' or not isinstance(value, str) or not value.startswith(PREFIX):
        return value                      # khali ya purana plaintext
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError):
        logger.error('Encrypted field decrypt nahi hua (DATA_ENCRYPTION_KEY galat ya badli hui?).')
        return _Undecryptable(value)


class EncryptedTextField(models.TextField):
    """TextField jis ki value database mein encrypted rehti hai."""
    description = 'Encrypted text'

    def from_db_value(self, value, expression, connection):
        return decrypt_value(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_value(value)


class EncryptedCharField(EncryptedTextField):
    """CharField jaisa (form mein single-line input + max_length check), lekin DB mein encrypted text."""
    description = 'Encrypted char'

    def __init__(self, *args, max_length=None, **kwargs):
        self.form_max_length = max_length
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.form_max_length is not None:
            kwargs['max_length'] = self.form_max_length
        return name, path, args, kwargs

    def formfield(self, **kwargs):
        kwargs.setdefault('max_length', self.form_max_length)
        kwargs.setdefault('widget', forms.TextInput)
        return super(models.TextField, self).formfield(**{'form_class': forms.CharField, **kwargs})

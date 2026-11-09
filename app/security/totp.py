"""
Authenticator-app two-factor codes (TOTP, RFC 6238) and one-time backup codes.

Pure standard library: works with Google Authenticator, Microsoft Authenticator,
Authy, 1Password, etc. No new pip package and no new migration are needed -
the secret and the hashed backup codes live in User2FASettings.secret_key /
User2FASettings.backup_codes, which already exist.

The secret is stored encrypted (security/field_crypto.py). Backup codes are
stored only as SHA-256 hashes and can be used once.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

PERIOD = 30
DIGITS = 6
WINDOW = 1                 # accept the previous / next 30 s step (clock drift)
BACKUP_CODE_COUNT = 10


# ----------------------------------------------------------------- pure TOTP --
def generate_secret():
    """Random 160-bit secret, base32 encoded (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _hotp(secret_b32, counter):
    key = base64.b32decode(secret_b32.replace(" ", "").upper(), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return f"{code:0{DIGITS}d}"


def totp_at(secret_b32, for_time=None):
    return _hotp(secret_b32, int((time.time() if for_time is None else for_time) // PERIOD))


def verify_totp(secret_b32, code, for_time=None, window=WINDOW):
    """Return the matching time-step counter, or None. Constant-time compare."""
    code = (code or "").replace(" ", "").strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    now_step = int((time.time() if for_time is None else for_time) // PERIOD)
    matched = None
    for step in range(now_step - window, now_step + window + 1):
        if hmac.compare_digest(_hotp(secret_b32, step), code):
            matched = step
    return matched


def provisioning_uri(secret_b32, account, issuer="ERP System"):
    """otpauth:// URI - can be turned into a QR code or opened by a phone app."""
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")


# ------------------------------------------------------------- backup codes --
def _hash_backup(code):
    return hashlib.sha256(code.replace("-", "").strip().lower().encode()).hexdigest()


def new_backup_codes(count=BACKUP_CODE_COUNT):
    """Return (plain_codes_to_show_once, hashes_to_store)."""
    plain = []
    for _ in range(count):
        raw = secrets.token_hex(4)                 # 8 hex chars
        plain.append(f"{raw[:4]}-{raw[4:]}")
    return plain, [_hash_backup(c) for c in plain]


def consume_backup_code(stored_hashes, code):
    """Return the new list of hashes if `code` was valid (one use), else None."""
    candidate = _hash_backup(code or "")
    found = None
    for h in stored_hashes or []:
        if hmac.compare_digest(h, candidate):
            found = h
    if found is None:
        return None
    remaining = list(stored_hashes)
    remaining.remove(found)
    return remaining


# ------------------------------------------------- database helpers (Django) --
def get_totp_secret(user_settings):
    """Decrypted secret of a User2FASettings row ('' if none)."""
    from .field_crypto import decrypt_value
    raw = user_settings.secret_key or ""
    return decrypt_value(raw) if raw else ""


def set_totp_secret(user_settings, secret_b32):
    from .field_crypto import encrypt_value
    user_settings.secret_key = encrypt_value(secret_b32)


def user_has_totp(user):
    """True when the user finished authenticator setup."""
    from app.models import User2FASettings
    s = User2FASettings.objects.filter(user=user).first()
    return bool(s and s.is_2fa_enabled and s.secret_key and s.verified_at)


def check_user_code(user, code):
    """Verify an authenticator code OR a backup code for the user.

    Returns (ok, used_backup). Brute force is limited per user (cache counter),
    and a TOTP code cannot be replayed inside its validity window.
    """
    from django.core.cache import cache
    from app.models import User2FASettings

    fail_key = f"totp_fail:{user.pk}"
    if cache.get(fail_key, 0) >= 5:
        return False, False

    s = User2FASettings.objects.filter(user=user).first()
    if not s or not s.secret_key:
        return False, False

    step = verify_totp(get_totp_secret(s), code)
    if step is not None:
        replay_key = f"totp_used:{user.pk}:{step}"
        if cache.add(replay_key, 1, PERIOD * (2 * WINDOW + 2)):
            cache.delete(fail_key)
            return True, False
        return False, False                         # same code used twice

    remaining = consume_backup_code(s.backup_codes, code)
    if remaining is not None:
        s.backup_codes = remaining
        s.save(update_fields=["backup_codes", "updated_at"])
        cache.delete(fail_key)
        return True, True

    if cache.add(fail_key, 1, 300):
        pass
    else:
        try:
            cache.incr(fail_key)
        except ValueError:
            cache.set(fail_key, 1, 300)
    return False, False

"""Portal passwords (customer, vendor, rider, shareholder) ke liye ek hi qaida.

Staff/admin ka policy alag hai (SecuritySettings + validate_password_strength). Yahan wahi cheezein
check hoti hain jo ek aam user ke liye zaroori hain: lambai, harf + number, aam (common) passwords,
aur naam/phone/username se milta hua na ho.
"""
import re

from django.conf import settings
from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError

MIN_LENGTH = int(getattr(settings, 'PORTAL_PASSWORD_MIN_LENGTH', 8))
MAX_LENGTH = 128

_common = CommonPasswordValidator()


def password_errors(password, hints=()):
    """Masle ki list (khali = password theek). hints = naam, phone, username, email jaisi cheezein."""
    pw = password or ''
    errors = []
    if len(pw) < MIN_LENGTH:
        errors.append(f'Password kam az kam {MIN_LENGTH} characters ka ho.')
    if len(pw) > MAX_LENGTH:
        errors.append(f'Password {MAX_LENGTH} characters se lamba na ho.')
    if pw and not (re.search(r'[A-Za-z]', pw) and re.search(r'\d', pw)):
        errors.append('Password mein kam az kam ek harf aur ek number ho.')
    if pw and len(set(pw)) <= 2:
        errors.append('Password mein sirf ek-do characters dohraye na hon.')
    try:
        _common.validate(pw)
    except ValidationError:
        errors.append('Yeh password bohat aam hai, koi mushkil password chunein.')

    low = pw.lower()
    digits = re.sub(r'\D', '', pw)
    for h in hints:
        h = str(h or '').strip().lower()
        if not h:
            continue
        h_digits = re.sub(r'\D', '', h)
        if (len(h) >= 4 and h in low) or (len(h_digits) >= 6 and h_digits[-8:] in digits):
            errors.append('Password mein apna naam, phone ya username na rakhein.')
            break
    return errors


def first_error(password, hints=()):
    errs = password_errors(password, hints)
    return errs[0] if errs else None

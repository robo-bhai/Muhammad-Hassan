"""Phone number helpers for duplicate control (customers + vendors).

Ek hi number kai tarah likha jata hai:  0300-1234567 / 03001234567 / +92 300 1234567 / 923001234567.
`phone_key()` in sab ko ek hi key deta hai ('923001234567'), is liye duplicate check format se
dhoka nahi khata. Database mein number waisa hi rehta hai jaisa likha gaya (WhatsApp link, SMS,
print sab usi par chalte hain) - sirf muqabla key se hota hai.

Is file mein Django ka koi import nahi, taake pure tests seedha chal saken.
"""
import re

MIN_DIGITS = 8     # isse chhota number muqabla karne ke qabil nahi (galat match ka khatra)
MAX_DIGITS = 15    # E.164 ki had


def phone_key(raw):
    """Number ki digits-only canonical key. Pakistani number -> '92XXXXXXXXXX'. Khali/bekaar -> ''."""
    digits = re.sub(r'\D', '', str(raw or ''))
    if not digits:
        return ''
    if digits.startswith('00'):            # 0092300... -> 92300...
        digits = digits[2:]
    if digits.startswith('92') and len(digits) >= 11:
        return digits
    if digits.startswith('0') and 10 <= len(digits) <= 11:     # 0300... -> 92300...
        return '92' + digits[1:]
    if len(digits) == 10 and digits.startswith('3'):           # 300... -> 92300...
        return '92' + digits
    return digits


def is_comparable(raw):
    k = phone_key(raw)
    return MIN_DIGITS <= len(k) <= MAX_DIGITS


def same_phone(a, b):
    ka, kb = phone_key(a), phone_key(b)
    return bool(ka) and ka == kb and is_comparable(a)


def find_by_phone(model, raw, exclude_pk=None, field='contact_number'):
    """Is number wale saare records (kisi bhi format mein saved) ki list. Bekaar/chhota number -> []."""
    key = phone_key(raw)
    if not (MIN_DIGITS <= len(key) <= MAX_DIGITS):
        return []
    qs = (model.objects.filter(**{f'{field}__isnull': False})
          .exclude(**{field: ''})
          .filter(**{f'{field}__contains': key[-3:]}))      # sasta pehla chhanna, phir sahi muqabla
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return [o for o in qs if phone_key(getattr(o, field)) == key]


def phone_changed(old, new):
    """Edit ke waqt: number sach mein badla? (sirf format badalne par duplicate check nahi chalta)"""
    return phone_key(old) != phone_key(new)


def group_duplicates(rows, key_fn):
    """rows: dicts ki list. key_fn(row) -> key ('' = ignore). Wapas: sirf woh groups jinme 2+ rows hon."""
    groups = {}
    for row in rows:
        k = key_fn(row)
        if k:
            groups.setdefault(k, []).append(row)
    return [{'key': k, 'rows': v} for k, v in sorted(groups.items()) if len(v) > 1]

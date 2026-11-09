"""Cart ke liye product options (size / extras) ke chhote madadgar.

Cart session mein `{cart_key: item}` hota hai. Bina options ka item pehle ki tarah str(product_id) key
par rehta hai (purana cart waisa hi chalta hai). Options wala item "pid:optid-optid" key par, taake ek
hi product alag options ke sath alag line bane (Large aur Small pizza do line).
"""
import hashlib
import re

CART_KEY_RE = re.compile(r'^\d+(:[0-9-]*(:[0-9a-f]{8})?)?$')


def option_key(option_ids):
    """Chune hue option ids ki tarteeb-bari-bari wali key: [5, 2] -> '2-5'."""
    return '-'.join(str(i) for i in sorted(int(i) for i in (option_ids or [])))


def clean_note(raw):
    """Special instruction: ek line, ziyada se ziyada 200 harf."""
    return ' '.join(str(raw or '').split())[:200]


def note_hash(note):
    return hashlib.md5(clean_note(note).lower().encode('utf-8')).hexdigest()[:8]


def make_cart_key(product_id, option_ids=None, note=''):
    """'12' (kuch nahi), '12:3-7' (options), '12:3-7:ab12cd34' ya '12::ab12cd34' (note ke sath).
    Alag note = alag line, taake do alag instructions mix na hon."""
    key = option_key(option_ids)
    if clean_note(note):
        return f"{int(product_id)}:{key}:{note_hash(note)}"
    return f"{int(product_id)}:{key}" if key else str(int(product_id))


def order_line_key(option_ids, note=''):
    """SaleOrderItem.options_key: ek order mein ek hi product ki alag options/notes wali lines ko alag rakhta hai."""
    key = option_key(option_ids)
    return f"{key}:{note_hash(note)}" if clean_note(note) else key


def is_valid_cart_key(key):
    return bool(CART_KEY_RE.match(str(key)))


def options_text(options):
    """Options ke naam ek line mein: 'Large, Extra cheese'."""
    return ', '.join(o.name for o in (options or []))


def parse_option_ids(raw):
    """JSON list ya '1,2,3' string se int ids (kharab values chhor deta hai)."""
    if raw is None or raw == '':
        return []
    if isinstance(raw, str):
        raw = raw.split(',')
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]
    ids = []
    for v in raw:
        try:
            ids.append(int(v))
        except (TypeError, ValueError):
            continue
    return ids


def units_in_cart(cart, product_id):
    """Is product ki cart mein kul qty (saari option lines milakar)."""
    total = 0
    for item in (cart or {}).values():
        try:
            if int(item.get('product_id')) == int(product_id):
                total += int(item.get('quantity', 0))
        except (TypeError, ValueError):
            continue
    return total

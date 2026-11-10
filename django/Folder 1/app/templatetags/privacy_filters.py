"""Privacy template filters.   {% load privacy_filters %}   {{ phone|mask_phone }}"""
from django import template

register = template.Library()


@register.filter
def mask_phone(value, keep=3):
    """'03001234567' -> '0300••••567' (pehle 4 aur aakhri 3 digits)."""
    s = str(value or '').strip()
    if not s:
        return ''
    keep = int(keep)
    if len(s) <= 4 + keep:
        return '•' * len(s)
    return s[:4] + '•' * (len(s) - 4 - keep) + s[-keep:]

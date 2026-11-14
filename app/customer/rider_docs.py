"""Rider ke documents ka hisaab (pure functions, DB ke bina).

Talabat Bahrain jaisa onboarding: rider CPR, driving licence, vehicle registration aur apni photo upload
karta hai; admin har document approve/reject karta hai; sab zaroori documents approve hon to rider approved.
"""
from datetime import timedelta

# (kind, label, expiry chahiye?, number chahiye?)
KINDS = [
    ('cpr',     'CPR / ID card',        True,  True),
    ('license', 'Driving licence',      True,  True),
    ('vehicle', 'Vehicle registration', True,  False),
    ('photo',   'Apni photo (selfie)',  False, False),
]
KIND_LABELS = {k: label for k, label, _e, _n in KINDS}
REQUIRED = ['cpr', 'license', 'vehicle', 'photo']
NEEDS_EXPIRY = {k for k, _l, e, _n in KINDS if e}
NEEDS_NUMBER = {k for k, _l, _e, n in KINDS if n}
SOON_DAYS = 30


def evaluate(docs, today, required=None, soon_days=SOON_DAYS):
    """docs: [{'kind','status' (pending/approved/rejected),'expiry' (date|None)}].
    Return dict: missing/pending/rejected/approved/expired/expiring (kind ki lists) aur complete (bool)."""
    required = list(required or REQUIRED)
    by = {d['kind']: d for d in docs}
    out = {'missing': [], 'pending': [], 'rejected': [], 'approved': [], 'expired': [], 'expiring': []}
    soon = today + timedelta(days=soon_days)
    for k in required:
        d = by.get(k)
        if d is None:
            out['missing'].append(k)
            continue
        out[d['status'] if d['status'] in ('pending', 'approved', 'rejected') else 'pending'].append(k)
        exp = d.get('expiry')
        if exp:
            if exp < today:
                out['expired'].append(k)
            elif exp <= soon:
                out['expiring'].append(k)
    out['complete'] = (not out['missing'] and len(out['approved']) == len(required) and not out['expired'])
    return out


def blocking(ev):
    """Approved rider ko kaam se rokne wale masle: rad kiya hua ya expire document."""
    return sorted(set(ev['rejected']) | set(ev['expired']))

"""Vendor (store) documents ka hisaab - pure functions, DB ke bina (seedha test ho sakte hain).

Talabat Bahrain jaisa onboarding: store CR (commercial registration), owner ka CPR/ID, bank/IBAN proof
upload karta hai (zaroori); VAT certificate aur food/health licence optional hain (agar upload hon to
unki expiry bhi dekhi jati hai). Admin har document approve/reject karta hai.
"""
from datetime import timedelta

# (kind, label, expiry chahiye?, number chahiye?, zaroori?)
KINDS = [
    ('cr',       'Commercial Registration (CR)',   True,  True,  True),
    ('owner_id', 'Owner CPR / ID card',            True,  True,  True),
    ('bank',     'Bank / IBAN proof',              False, False, True),
    ('vat',      'VAT certificate',                False, True,  False),
    ('health',   'Food / health licence',          True,  False, False),
]
KIND_LABELS = {k: label for k, label, _e, _n, _r in KINDS}
REQUIRED = [k for k, _l, _e, _n, r in KINDS if r]
NEEDS_EXPIRY = {k for k, _l, e, _n, _r in KINDS if e}
NEEDS_NUMBER = {k for k, _l, _e, n, _r in KINDS if n}
SOON_DAYS = 30


def evaluate(docs, today, required=None, soon_days=SOON_DAYS):
    """docs: [{'kind','status' (pending/approved/rejected),'expiry' (date|None)}].

    Wapas dict: missing / pending / rejected / approved / expired / expiring (kind ki lists) aur
    complete (bool: sab zaroori approved, aur koi upload kiya hua document expire nahi).
    Optional kinds sirf tab dekhe jate hain jab upload hon (missing nahi ginte)."""
    required = list(REQUIRED if required is None else required)
    by = {d['kind']: d for d in docs if d.get('kind') in KIND_LABELS}
    out = {'missing': [], 'pending': [], 'rejected': [], 'approved': [], 'expired': [], 'expiring': []}
    soon = today + timedelta(days=soon_days)
    for k in [x for x, *_ in KINDS]:
        d = by.get(k)
        if d is None:
            if k in required:
                out['missing'].append(k)
            continue
        st = d.get('status')
        out[st if st in ('pending', 'approved', 'rejected') else 'pending'].append(k)
        exp = d.get('expiry')
        if exp:
            if exp < today:
                out['expired'].append(k)
            elif exp <= soon:
                out['expiring'].append(k)
    approved_required = [k for k in required if k in out['approved']]
    out['complete'] = (not out['missing'] and len(approved_required) == len(required) and not out['expired'])
    return out


def blocking(ev):
    """Approved store ko rokne wale masle: rad kiya hua ya expire document."""
    return sorted(set(ev['rejected']) | set(ev['expired']))


def summary(ev, required=None):
    """Admin list ke liye chhota text, jaise '2/3 approved · 1 pending · 1 expiring'."""
    required = list(REQUIRED if required is None else required)
    done = sum(1 for k in required if k in ev['approved'])
    parts = [f'{done}/{len(required)} approved']
    for key, label in (('pending', 'pending'), ('rejected', 'rejected'), ('missing', 'missing'),
                       ('expired', 'expired'), ('expiring', 'expiring')):
        if ev[key]:
            parts.append(f'{len(ev[key])} {label}')
    return ' · '.join(parts)


def warnings(ev):
    """Vendor ko dikhane ke liye: (level, text) ki list; level 'danger' ya 'warning'."""
    out = [('danger', f'{KIND_LABELS[k]} has expired - upload a new one.') for k in ev['expired']]
    out += [('danger', f'{KIND_LABELS[k]} was rejected - please upload it again.')
            for k in ev['rejected'] if k not in ev['expired']]
    out += [('warning', f'{KIND_LABELS[k]} expires soon.') for k in ev['expiring']]
    return out

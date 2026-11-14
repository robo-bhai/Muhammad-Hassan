"""Rider goals/bonus aur cash-in-hand limit (pure functions, DB ke bina)."""
from datetime import timedelta
from decimal import Decimal

CASH_WARN_AT = 0.8      # limit ka 80% par peeli warning


def week_start(d):
    """Hafta Peer (Monday) se shuru."""
    return d - timedelta(days=d.weekday())


def progress(done, goal, bonus):
    """Goal off (goal <= 0) ho to None. Warna {'done','goal','bonus','pct','left','reached'}."""
    goal = int(goal or 0)
    if goal <= 0:
        return None
    done = int(done or 0)
    return {'done': done, 'goal': goal, 'bonus': Decimal(bonus or 0),
            'pct': min(100, int(done * 100 / goal)), 'left': max(0, goal - done),
            'reached': done >= goal}


def cash_state(cash, limit):
    """Rider ke paas COD cash vs admin ki hadd. limit <= 0 = band.
    level: 'ok' | 'warn' (80%+) | 'over' (hadd paar)."""
    limit = Decimal(limit or 0)
    cash = Decimal(cash or 0)
    if limit <= 0:
        return None
    pct = min(100, int(cash * 100 / limit)) if cash > 0 else 0
    level = 'over' if cash >= limit else ('warn' if cash >= limit * Decimal(str(CASH_WARN_AT)) else 'ok')
    return {'cash': cash, 'limit': limit, 'pct': pct, 'level': level}

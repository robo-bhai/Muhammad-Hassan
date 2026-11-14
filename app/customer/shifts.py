"""Rider shift booking ka hisaab (pure functions, DB ke bina). Sab waqt naive local datetime."""
from datetime import datetime, timedelta, time

MAX_SLOTS_PER_CALL = 8


def bounds(d, start, end):
    """Shift ka (shuru, khatam) datetime. end <= start ho to shift aadhi raat ke baad khatam (agle din)."""
    s = datetime.combine(d, start)
    e = datetime.combine(d, end)
    if e <= s:
        e += timedelta(days=1)
    return s, e


def overlaps(a, b):
    """a, b = (shuru, khatam). Sirf chhune wali shifts overlap nahi."""
    return a[0] < b[1] and b[0] < a[1]


def can_cancel(start_dt, now, hours):
    """Shift shuru hone se kam az kam `hours` pehle tak cancel ho sakti hai (hours=0: shuru hone tak)."""
    return now <= start_dt - timedelta(hours=hours)


def in_shift(windows, now, grace_minutes=15):
    """windows: [(shuru, khatam)]. Shuru se `grace` pehle se khatam tak 'shift mein' maana jata hai."""
    g = timedelta(minutes=grace_minutes)
    return any(s - g <= now <= e for s, e in windows)


def next_window(windows, now):
    """Abhi chal rahi ya agli shift (shuru, khatam), ya None."""
    live = [w for w in windows if w[1] >= now]
    return min(live, key=lambda w: w[0]) if live else None


def parse_slots(text):
    """'12:00-16:00, 18:00-23:00' -> [(time, time)]. Galat ho to ValueError. Zyada se zyada MAX_SLOTS_PER_CALL."""
    out = []
    for part in (text or '').replace('\n', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            a, b = part.replace('–', '-').split('-')
            s = time(*map(int, a.strip().split(':')))
            e = time(*map(int, b.strip().split(':')))
        except Exception:
            raise ValueError(f'Galat slot: "{part}" (aise likhein 12:00-16:00)')
        if s == e:
            raise ValueError(f'Slot "{part}" ka shuru aur khatam ek hi hai.')
        out.append((s, e))
    if not out:
        raise ValueError('Kam az kam ek slot likhein, jaise 12:00-16:00')
    if len(out) > MAX_SLOTS_PER_CALL:
        raise ValueError(f'Ek baar mein zyada se zyada {MAX_SLOTS_PER_CALL} slots.')
    return out

"""Offline queue se aane wali rider location ka faisla (pure, DB ke bina).

Phone offline ho to location queue mein jati hai aur internet aane par `at` (epoch seconds, jab li gayi)
ke saath bheji jati hai. Server sirf *last* location rakhta hai, isliye purani point naye ko kabhi
overwrite nahi karni chahiye.
"""
import math

MAX_AGE_SECONDS = 6 * 3600      # isse purani point bekaar
CLOCK_SKEW_SECONDS = 60         # phone ki ghari thori aage ho to theek


def resolve_capture(at_raw, now_ts, last_ts, min_gap=3):
    """Return (captured_ts, reason). captured_ts None = update chhod do (reason: too_old|older|rate).
    at_raw None/kharab = live point (abhi li gayi)."""
    captured = now_ts
    if at_raw not in (None, ''):
        try:
            at = float(at_raw)
        except (TypeError, ValueError):
            at = None
        if at is not None and math.isfinite(at):
            captured = min(at, now_ts) if at <= now_ts + CLOCK_SKEW_SECONDS else now_ts
    if now_ts - captured > MAX_AGE_SECONDS:
        return None, 'too_old'
    if last_ts is not None:
        if captured <= last_ts:
            return None, 'older'
        if captured - last_ts < min_gap:
            return None, 'rate'
    return captured, 'ok'

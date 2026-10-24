"""Exchange trading calendars for A-shares (XSHG), Hong Kong (XHKG) and 港股通 (both open).

Uses the maintained ``exchange_calendars`` package when it is installed (pip install
exchange_calendars). Without it, falls back to weekdays minus a small built-in holiday list and
reports ``source = "weekday_fallback"`` so callers can warn that holidays are not exact.

Note: the real 港股通 calendar also closes on a few days around mainland/HK holidays when
settlement is not possible; the intersection of the two exchange calendars is a close but not
exact approximation.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

try:  # optional dependency
    import exchange_calendars as _xcals  # type: ignore
except Exception:  # pragma: no cover - depends on environment
    _xcals = None


CALENDAR_BY_MARKET = {"a_share": "XSHG", "hk_stock": "XHKG", "hk_connect": "XHKG&XSHG"}

# Minimal fallback (used only when exchange_calendars is unavailable).
_FALLBACK_HOLIDAYS = {
    "XSHG": {
        *[date(2024, 1, 1), date(2024, 4, 4), date(2024, 4, 5), date(2024, 6, 10), date(2024, 9, 16), date(2024, 9, 17)],
        *[date(2024, 2, d) for d in range(9, 18)],
        *[date(2024, 5, d) for d in range(1, 6)],
        *[date(2024, 10, d) for d in range(1, 8)],
    },
    "XHKG": set(),
}


def calendar_available() -> bool:
    return _xcals is not None


def calendar_name(market: str) -> str:
    return CALENDAR_BY_MARKET.get(market, "XSHG")


@lru_cache(maxsize=32)
def _sessions(code: str, start: date, end: date) -> tuple[frozenset[date], str]:
    if "&" in code:
        sets = [_sessions(part, start, end) for part in code.split("&")]
        days = frozenset.intersection(*(item[0] for item in sets))
        source = "exchange_calendars" if all(item[1] == "exchange_calendars" for item in sets) else "weekday_fallback"
        return days, source
    if _xcals is not None:
        try:
            cal = _xcals.get_calendar(code)
            first = max(start, cal.first_session.date())
            last = min(end, cal.last_session.date())
            days: set[date] = set()
            if first <= last:
                days = {ts.date() for ts in cal.sessions_in_range(first.isoformat(), last.isoformat())}
            # Outside the calendar's coverage fall back to weekdays.
            cursor = start
            while cursor <= end:
                if (cursor < first or cursor > last) and cursor.weekday() < 5:
                    days.add(cursor)
                cursor += timedelta(days=1)
            return frozenset(days), "exchange_calendars"
        except Exception:
            pass
    holidays = _FALLBACK_HOLIDAYS.get(code, set())
    days = set()
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in holidays:
            days.add(cursor)
        cursor += timedelta(days=1)
    return frozenset(days), "weekday_fallback"


def trading_days(market: str, start: date, end: date) -> tuple[frozenset[date], str]:
    """(set of trading days in [start, end], source)."""
    if end < start:
        return frozenset(), "empty"
    return _sessions(calendar_name(market), start, end)


def is_trading_day(market: str, day: date) -> bool:
    return day in trading_days(market, day, day)[0]


def expected_trading_days(market: str, start: date, end: date) -> list[date]:
    return sorted(trading_days(market, start, end)[0])


def missing_trading_days(market: str, previous_day: date, current_day: date) -> list[date]:
    if current_day <= previous_day + timedelta(days=1):
        return []
    return expected_trading_days(market, previous_day + timedelta(days=1), current_day - timedelta(days=1))

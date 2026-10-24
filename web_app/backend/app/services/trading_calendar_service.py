"""Trading calendars for data-quality checks (A-share XSHG, HK XHKG, 港股通 = both open).

Delegates to market_rules_module.trading_calendar (exchange_calendars when installed; otherwise a
weekday fallback that the calendar label reports).
"""
from __future__ import annotations

import sys
from datetime import date

from app.services.legacy_paths import REPO_ROOT

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from market_rules_module import trading_calendar as _cal  # noqa: E402


def calendar_label(market: str | None) -> str:
    if market is None:
        return "per_instrument"
    source = "exchange_calendars" if _cal.calendar_available() else "weekday_fallback"
    return f"{_cal.calendar_name(market)}:{source}"


def is_trading_day(market: str, day: date) -> bool:
    return _cal.is_trading_day(market, day)


def expected_trading_days(market: str, start: date, end: date) -> list[date]:
    return _cal.expected_trading_days(market, start, end)


def missing_trading_days(market: str, previous_day: date, current_day: date) -> list[date]:
    return _cal.missing_trading_days(market, previous_day, current_day)


# Backwards-compatible A-share helpers.
def is_a_share_trading_day(day: date) -> bool:
    return is_trading_day("a_share", day)


def missing_a_share_trading_days(previous_day: date, current_day: date) -> list[date]:
    return missing_trading_days("a_share", previous_day, current_day)

"""Daily HKD->CNY reference rates (ECB data via the free Frankfurter API).

ECB rates are a close proxy for the 港股通 settlement rate; the actual settlement rate differs
slightly (set ``fx.spread`` in market_rules.json to model the difference).
"""
from __future__ import annotations

from typing import Any, Callable

from data_module.sources.http import get_json

URLS = ["https://api.frankfurter.dev/v1/{start}..{end}", "https://api.frankfurter.app/{start}..{end}"]
SOURCE = "frankfurter_ecb"


def fetch_rates(base: str, quote: str, start: str, end: str,
                fetch: Callable[[str, dict[str, Any]], Any] | None = None) -> dict[str, float]:
    """{'YYYY-MM-DD': rate} where rate = units of ``quote`` per 1 ``base``."""
    fetch = fetch or (lambda url, params: get_json(url, params))
    last_error: Exception | None = None
    for template in URLS:
        try:
            payload = fetch(template.format(start=start, end=end), {"from": base, "to": quote})
            rates = {day: float(values[quote]) for day, values in (payload.get("rates") or {}).items() if quote in values}
            if rates:
                return rates
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"could not load {base}{quote} rates: {last_error}")


def fetch_rates_by_year(base: str, quote: str, start: str, end: str,
                        fetch: Callable[[str, dict[str, Any]], Any] | None = None) -> dict[str, float]:
    """Same as fetch_rates, one request per calendar year (keeps responses small)."""
    rates: dict[str, float] = {}
    for year in range(int(start[:4]), int(end[:4]) + 1):
        a = max(start, f"{year}-01-01")
        b = min(end, f"{year}-12-31")
        rates.update(fetch_rates(base, quote, a, b, fetch))
    return rates

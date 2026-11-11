"""Daily bars from Tencent's public quote API (no token) for A-shares (SH/SZ/BJ) and HK stocks.

Two requests per year: raw (unadjusted) prices and forward-adjusted (前复权) prices. The engine
trades on raw prices. Ex-dates and dividend amounts are inferred from the gap between the two
series, and a proportional ``adj_factor`` (adjusted = raw * adj_factor, latest = 1) is rebuilt from
them, so signals on adjusted prices and dividend cash flows are consistent.

Endpoints (observed 2026-10):
  A-share raw : web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,START,END,N,      -> data.sh600519.day
  A-share qfq : web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,START,END,N,qfq   -> data.sh600519.qfqday
  HK raw      : web.ifzq.gtimg.cn/appstock/app/kline/kline?param=hk00700,day,START,END,N        -> data.hk00700.day
  HK qfq      : web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param=hk00700,day,START,END,N,qfq -> data.hk00700.qfqday
Rows: [date, open, close, high, low, volume, ...]. A-share volume is in lots of 100 shares.
These are unofficial endpoints; they can change without notice.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from data_module.adjust import factors_from_actions
from data_module.sources.http import get_bytes, get_json

KLINE_A = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
KLINE_HK_RAW = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
KLINE_HK_QFQ = "https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get"
QUOTE_URL = "https://qt.gtimg.cn/q="
SOURCE = "tencent"

Fetcher = Callable[[str, dict[str, Any]], Any]


def tencent_code(symbol: str) -> str:
    code, exchange = symbol.split(".")
    if exchange == "HK":
        return "hk" + code.zfill(5)
    return exchange.lower() + code


def _rows(payload: Any, code: str, key: str) -> list[list[Any]]:
    node = ((payload or {}).get("data") or {})
    if not isinstance(node, dict):
        return []
    node = node.get(code) or {}
    rows = node.get(key)
    if rows is None:  # some responses use e.g. 'qfqday' vs 'day' inconsistently
        rows = next((v for k, v in node.items() if k.endswith("day") and isinstance(v, list)), [])
    return rows or []


def _parse(rows: list[list[Any]], volume_multiplier: float) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        try:
            day = str(row[0])[:10]
            o, c, h, low = (float(row[i]) for i in (1, 2, 3, 4))
            volume = float(row[5]) * volume_multiplier if len(row) > 5 and row[5] not in (None, "") else 0.0
        except (IndexError, TypeError, ValueError):
            continue
        amount = 0.0
        if len(row) > 8:
            try:
                amount = float(row[8]) * 10_000  # HK turnover is in 10k HKD
            except (TypeError, ValueError):
                amount = 0.0
        out[day] = {"open": o, "close": c, "high": h, "low": low, "volume": volume, "amount": amount}
    return out


def _year_ranges(start: str, end: str) -> list[tuple[str, str]]:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    ranges = []
    for year in range(s.year, e.year + 1):
        a = max(s, date(year, 1, 1))
        b = min(e, date(year, 12, 31))
        ranges.append((a.isoformat(), b.isoformat()))
    return ranges


def fetch_daily(symbol: str, start: str, end: str, fetch: Fetcher | None = None) -> list[dict[str, Any]]:
    """Daily bars for ``symbol`` between start and end (inclusive): raw prices + proportional adj_factor."""
    return fetch_daily_with_actions(symbol, start, end, fetch)["bars"]


def fetch_daily_with_actions(symbol: str, start: str, end: str, fetch: Fetcher | None = None) -> dict[str, list[dict[str, Any]]]:
    """{'bars': [...], 'actions': [...]} — actions are dividend / bonus-share events inferred from the feed."""
    fetch = fetch or (lambda url, params: get_json(url, params))
    code = tencent_code(symbol)
    is_hk = symbol.endswith(".HK")
    multiplier = 1.0 if is_hk else 100.0
    raw: dict[str, dict[str, float]] = {}
    qfq: dict[str, dict[str, float]] = {}
    for a, b in _year_ranges(start, end):
        if is_hk:
            raw.update(_parse(_rows(fetch(KLINE_HK_RAW, {"param": f"{code},day,{a},{b},400"}), code, "day"), multiplier))
            qfq.update(_parse(_rows(fetch(KLINE_HK_QFQ, {"param": f"{code},day,{a},{b},400,qfq"}), code, "qfqday"), multiplier))
        else:
            raw.update(_parse(_rows(fetch(KLINE_A, {"param": f"{code},day,{a},{b},400,"}), code, "day"), multiplier))
            qfq.update(_parse(_rows(fetch(KLINE_A, {"param": f"{code},day,{a},{b},400,qfq"}), code, "qfqday"), multiplier))
    return merge_raw_and_adjusted(symbol, raw, qfq)


def fetch_index_daily(code: str, start: str, end: str, fetch: Fetcher | None = None) -> dict[str, float]:
    """{date: close} for an index by Tencent code, e.g. 'sh000300' (沪深300) or 'hkHSI' (恒生指数)."""
    fetch = fetch or (lambda url, params: get_json(url, params))
    url = KLINE_HK_RAW if code.startswith("hk") else KLINE_A
    closes: dict[str, float] = {}
    for a, b in _year_ranges(start, end):
        suffix = "" if code.startswith("hk") else ","
        rows = _rows(fetch(url, {"param": f"{code},day,{a},{b},400{suffix}"}), code, "day")
        closes.update({day: bar["close"] for day, bar in _parse(rows, 1.0).items() if bar["close"] > 0})
    return closes


DIFF_TOLERANCE = 0.0025  # Tencent prices have 3 decimals; smaller moves in (raw - qfq) are rounding


def detect_actions(raw: dict[str, dict[str, float]], qfq: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """Ex-dates where the gap between raw and adjusted prices changes.

    Tencent's 前复权 series is subtractive (adjusted = raw - later cash dividends), so on an ex-date the
    gap ``raw - qfq`` shrinks by the dividend per share. A gap change above 25% of the price is read as
    bonus/split shares instead: 1 + B = (qfq_t / qfq_{t-1}) * (raw_{t-1} / raw_t). Events that combine
    cash and bonus shares are approximated; import exact corporate actions where tax precision matters.
    """
    actions: list[dict[str, Any]] = []
    days = [d for d in sorted(raw) if d in qfq and raw[d]["close"] > 0 and qfq[d]["close"] > 0]
    for prev, day in zip(days, days[1:]):
        gap_prev = raw[prev]["close"] - qfq[prev]["close"]
        gap_now = raw[day]["close"] - qfq[day]["close"]
        change = gap_prev - gap_now
        if abs(change) <= DIFF_TOLERANCE + 1e-4 * raw[prev]["close"]:
            continue
        if change > 0 and change < 0.25 * raw[prev]["close"]:
            actions.append({"ex_date": day, "cash_dividend": round(change, 4), "bonus_ratio": 0.0})
            continue
        bonus = (qfq[day]["close"] / qfq[prev]["close"]) * (raw[prev]["close"] / raw[day]["close"]) - 1
        if bonus > 0.05:
            actions.append({"ex_date": day, "cash_dividend": 0.0, "bonus_ratio": round(bonus, 4)})
    return actions


def merge_raw_and_adjusted(symbol: str, raw: dict[str, dict[str, float]], qfq: dict[str, dict[str, float]]) -> dict[str, list[dict[str, Any]]]:
    actions = detect_actions(raw, qfq)
    days = [d for d in sorted(raw) if min(raw[d]["open"], raw[d]["high"], raw[d]["low"], raw[d]["close"]) > 0]
    factors = factors_from_actions(days, [raw[d]["close"] for d in days], actions)
    bars: list[dict[str, Any]] = []
    for day, factor in zip(days, factors):
        r = raw[day]
        high = max(r["high"], r["open"], r["close"])
        low = min(r["low"], r["open"], r["close"])
        amount = r["amount"] or (qfq.get(day, {}).get("amount") or 0.0)
        if not amount:
            amount = r["volume"] * (r["open"] + high + low + r["close"]) / 4  # estimate (not in the feed)
        bars.append(
            {
                "symbol": symbol, "frequency": "1d", "trade_time": day,
                "open": r["open"], "high": high, "low": low, "close": r["close"],
                "volume": r["volume"], "amount": round(amount, 2), "adj_factor": round(factor, 8), "source": SOURCE,
            }
        )
    return {"bars": bars, "actions": actions}


def fetch_name(symbol: str, fetch_bytes: Callable[[str], bytes] | None = None) -> str | None:
    fetch_bytes = fetch_bytes or (lambda url: get_bytes(url))
    code = tencent_code(symbol)
    try:
        text = fetch_bytes(QUOTE_URL + code).decode("gbk", errors="replace")
    except Exception:
        return None
    match = re.search(r'v_\w+="([^"]*)"', text)
    if not match:
        return None
    parts = match.group(1).split("~")
    return parts[1].strip() if len(parts) > 1 and parts[1].strip() else None


QUOTE_BATCH = 60  # codes per qt.gtimg.cn request


def _num(parts: list[str], index: int) -> float | None:
    try:
        value = float(parts[index])
    except (IndexError, ValueError):
        return None
    return value


def _quote_time(raw: str) -> str | None:
    """'20261027150003' (A-share) or '2026/10/27 16:08:12' (HK) -> '2026-10-27 15:00:03'."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 12:
        return None
    seconds = digits[12:14] or "00"
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}:{seconds}"


def parse_quote(symbol: str, line: str) -> dict[str, Any] | None:
    """One ``v_sh600519="1~贵州茅台~600519~price~prev_close~open~volume~..."`` record.

    Fields used: 1 name, 3 price, 4 previous close, 5 open, 6 volume (A-share lots of 100 / HK shares),
    30 time, 33 high, 34 low, 37 turnover (A-share in 10k CNY / HK in HKD).
    """
    parts = line.split("~")
    price, prev_close = _num(parts, 3), _num(parts, 4)
    if price is None or prev_close is None or len(parts) < 35:
        return None
    is_hk = symbol.endswith(".HK")
    volume = (_num(parts, 6) or 0.0) * (1 if is_hk else 100)
    amount = (_num(parts, 37) or 0.0) * (1 if is_hk else 10_000)
    open_, high, low = _num(parts, 5), _num(parts, 33), _num(parts, 34)
    traded = price > 0 and volume > 0
    return {
        "symbol": symbol,
        "name": parts[1].strip(),
        "price": price if price > 0 else prev_close,
        "prev_close": prev_close,
        "open": open_ if open_ else None,
        "high": high if high else None,
        "low": low if low else None,
        "volume": volume,
        "amount": round(amount, 2),
        "change": round(price - prev_close, 4) if traded and prev_close else 0.0,
        "change_pct": round(price / prev_close - 1, 6) if traded and prev_close else 0.0,
        "time": _quote_time(parts[30]) if len(parts) > 30 else None,
        "traded": traded,  # False before the open and for suspended stocks
    }


def fetch_quotes(symbols: list[str], fetch_bytes: Callable[[str], bytes] | None = None) -> dict[str, dict[str, Any]]:
    """Live quotes (about 3 s delayed) for many symbols, 60 per request."""
    fetch_bytes = fetch_bytes or (lambda url: get_bytes(url, timeout=8, retries=1))
    by_code = {tencent_code(s): s for s in symbols}
    out: dict[str, dict[str, Any]] = {}
    codes = list(by_code)
    for i in range(0, len(codes), QUOTE_BATCH):
        text = fetch_bytes(QUOTE_URL + ",".join(codes[i:i + QUOTE_BATCH])).decode("gbk", errors="replace")
        for code, body in re.findall(r'v_(\w+)="([^"]*)"', text):
            symbol = by_code.get(code)
            quote = parse_quote(symbol, body) if symbol else None
            if quote:
                out[symbol] = quote
    return out

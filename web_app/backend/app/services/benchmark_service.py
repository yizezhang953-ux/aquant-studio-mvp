"""Benchmark indices and the extra report analysis: index comparison, monthly returns, drawdown durations.

Everything here is computed when a report is opened, from the saved equity curve, so older
backtests get the same analysis once the index data is synced.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import MarketIndexBar
from app.services.market_data_source_service import tencent  # noqa: F401  (module with its path set up)

INDICES: dict[str, dict[str, str]] = {
    "HSI": {"name": "恒生指数", "tencent": "hkHSI", "market": "hk"},
    "CSI300": {"name": "沪深300", "tencent": "sh000300", "market": "a"},
}


# --------------------------------------------------------------------------- index data

def fetch_index_closes(code: str, start: str, end: str, provider_id: str) -> dict[str, float]:
    if provider_id == "demo":
        out: dict[str, float] = {}
        cursor, end_day, i = date.fromisoformat(start), date.fromisoformat(end), 0
        base, cycle = (20000.0, 60) if code == "HSI" else (4000.0, 90)
        while cursor <= end_day:
            if cursor.weekday() < 5:
                out[cursor.isoformat()] = round(base * (1 + 0.00015 * i * (1 if code == "HSI" else -0.3)
                                                        + 0.05 * ((i % cycle) / cycle - 0.5)), 2)
                i += 1
            cursor = date.fromordinal(cursor.toordinal() + 1)
        return out
    if provider_id != "tencent":
        raise ValueError(f"unknown data source {provider_id}")
    if not settings.market_data_network_enabled:
        raise ValueError("network data sources are disabled (MARKET_DATA_NETWORK_ENABLED=false)")
    try:
        return tencent.fetch_index_daily(INDICES[code]["tencent"], start, end)
    except RuntimeError as exc:
        raise ValueError(f"tencent request failed: {exc}") from exc


def save_index_closes(db: Session, code: str, closes: dict[str, float], source: str) -> int:
    existing = {row.trade_date: row for row in db.scalars(
        select(MarketIndexBar).where(MarketIndexBar.index_code == code, MarketIndexBar.trade_date.in_(list(closes))))}
    for day, close in closes.items():
        if day in existing:
            existing[day].close = close
            existing[day].source = source
        else:
            db.add(MarketIndexBar(index_code=code, trade_date=day, close=close, source=source))
    db.commit()
    return len(closes)


def sync_indices(db: Session, start: str, end: str, provider_id: str = "tencent") -> list[dict[str, Any]]:
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    results = []
    for code in INDICES:
        try:
            closes = fetch_index_closes(code, start, end, provider_id)
            if not closes:
                raise ValueError("数据源没有返回数据")
            results.append({"code": code, "name": INDICES[code]["name"], "ok": True,
                            "bars": save_index_closes(db, code, closes, provider_id), "error": None})
        except ValueError as exc:
            results.append({"code": code, "name": INDICES[code]["name"], "ok": False, "bars": 0, "error": str(exc)})
    return results


def index_status(db: Session) -> list[dict[str, Any]]:
    rows = {code: (first, last, count) for code, first, last, count in db.execute(
        select(MarketIndexBar.index_code, func.min(MarketIndexBar.trade_date), func.max(MarketIndexBar.trade_date),
               func.count()).group_by(MarketIndexBar.index_code))}
    return [{"code": code, "name": spec["name"], "start": rows.get(code, (None,))[0],
             "end": rows.get(code, (None, None))[1], "bars": rows.get(code, (None, None, 0))[2]}
            for code, spec in INDICES.items()]


# --------------------------------------------------------------------------- report analysis

def daily_equity(curve: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """Last equity of each day (intraday curves collapse to one point per day)."""
    by_day: dict[str, float] = {}
    for point in curve:
        by_day[str(point["trade_time"])[:10]] = float(point["equity"])
    return sorted(by_day.items())


def monthly_returns(days: list[tuple[str, float]], initial: float) -> list[dict[str, Any]]:
    month_end: dict[str, float] = {}
    for day, equity in days:
        month_end[day[:7]] = equity
    years: dict[int, dict[str, Any]] = {}
    previous = initial
    year_start: dict[int, float] = {}
    for month, equity in sorted(month_end.items()):
        year, m = int(month[:4]), int(month[5:7])
        row = years.setdefault(year, {"year": year, "months": [None] * 12, "total": None})
        year_start.setdefault(year, previous)
        row["months"][m - 1] = round(equity / previous - 1, 6) if previous else None
        row["total"] = round(equity / year_start[year] - 1, 6) if year_start[year] else None
        previous = equity
    return [years[y] for y in sorted(years)]


def drawdown_episodes(days: list[tuple[str, float]]) -> list[dict[str, Any]]:
    """Each stretch below a previous high: when it started, its low, and when (if) it was recovered."""
    episodes: list[dict[str, Any]] = []
    peak_day, peak = None, None
    current: dict[str, Any] | None = None
    for day, equity in days:
        if peak is None or equity >= peak:
            if current is not None:
                current.update(end=day, recovered=True)
                episodes.append(current)
                current = None
            peak_day, peak = day, equity
            continue
        depth = (peak - equity) / peak if peak else 0.0
        if current is None:
            current = {"start": peak_day, "trough": day, "depth": depth, "end": None, "recovered": False}
        elif depth > current["depth"]:
            current.update(trough=day, depth=depth)
    if current is not None:
        current["end"] = days[-1][0]
        episodes.append(current)
    for episode in episodes:
        start, trough, end = (date.fromisoformat(episode[k]) for k in ("start", "trough", "end"))
        episode.update(depth=round(episode["depth"], 6), days=(end - start).days,
                       fall_days=(trough - start).days, recover_days=(end - trough).days if episode["recovered"] else None)
    return episodes


def drawdown_summary(days: list[tuple[str, float]]) -> dict[str, Any]:
    episodes = [e for e in drawdown_episodes(days) if e["depth"] > 0.0005]  # ignore rounding-size dips
    total_days = (date.fromisoformat(days[-1][0]) - date.fromisoformat(days[0][0])).days if len(days) > 1 else 0
    underwater = sum(e["days"] for e in episodes)
    return {
        "longest": max(episodes, key=lambda e: e["days"]) if episodes else None,
        "deepest": max(episodes, key=lambda e: e["depth"]) if episodes else None,
        "count": len(episodes),
        "underwater_pct": round(underwater / total_days, 4) if total_days else None,
    }


def index_comparison(db: Session, days: list[tuple[str, float]], market: str | None,
                     strategy_return: float | None) -> list[dict[str, Any]]:
    if not days:
        return []
    first, last = days[0][0], days[-1][0]
    order = ["HSI", "CSI300"] if market in ("hk_stock", "hk_connect") else ["CSI300", "HSI"]
    out = []
    for code in order:
        start_row = db.scalars(select(MarketIndexBar).where(MarketIndexBar.index_code == code,
                                                            MarketIndexBar.trade_date <= first)
                               .order_by(MarketIndexBar.trade_date.desc()).limit(1)).first()
        rows = db.scalars(select(MarketIndexBar).where(MarketIndexBar.index_code == code,
                                                       MarketIndexBar.trade_date > first,
                                                       MarketIndexBar.trade_date <= last)
                          .order_by(MarketIndexBar.trade_date)).all()
        entry: dict[str, Any] = {"code": code, "name": INDICES[code]["name"], "available": False}
        # usable only when the index covers the whole report (a few days of slack at either end)
        if start_row is None or not rows or (date.fromisoformat(first) - date.fromisoformat(start_row.trade_date)).days > 10 \
                or (date.fromisoformat(last) - date.fromisoformat(rows[-1].trade_date)).days > 10:
            out.append(entry)
            continue
        closes = [(start_row.trade_date, start_row.close)] + [(r.trade_date, r.close) for r in rows]
        base = start_row.close
        values, j, current = [], 0, base
        for day, _ in days:  # index value on each report day, carried forward over index holidays
            while j < len(closes) and closes[j][0] <= day:
                current = closes[j][1]
                j += 1
            values.append(round(current / base, 6))
        total = values[-1] - 1
        span_years = (date.fromisoformat(last) - date.fromisoformat(first)).days / 365.25
        entry.update(available=True, total_return=round(total, 6),
                     annualized_return=round((1 + total) ** (1 / span_years) - 1, 6) if span_years >= 1 else None,
                     excess_return=round(strategy_return - total, 6) if strategy_return is not None else None,
                     growth=values)
        out.append(entry)
    return out


def report_analysis(db: Session, report: dict[str, Any]) -> dict[str, Any]:
    days = daily_equity(report.get("equity_curve") or [])
    metrics = report.get("metrics") or {}
    initial = float(metrics.get("initial_cash") or (days[0][1] if days else 0) or 0)
    return {
        "days": [d for d, _ in days],
        "benchmarks": index_comparison(db, days, report.get("market"), metrics.get("total_return")),
        "monthly_returns": monthly_returns(days, initial) if days else [],
        "drawdown": drawdown_summary(days) if days else None,
    }

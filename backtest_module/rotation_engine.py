"""Cross-sectional rotation backtest: score every sector, hold the top N with equal weights,
rebalance every week (or month), compare with the equal-weight basket of all sectors.

Timing follows the usual sell-side convention: the factor is read after the close of the last
trading day of the period, and the portfolio is switched at the close of the next trading day.
Between rebalances the weights drift with prices. Everything works on a (days x sectors) panel.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

TRADING_DAYS = 252

FACTORS = {
    "net_active_buy": "主动净买入（主动买入占比 − 主动卖出占比，除以成交额占比）",
    "momentum": "动量（过去 W 日涨幅）",
    "reversal": "反转（过去 W 日跌幅）",
    "turnover": "换手（成交额 ÷ 流通市值）",
}
# panel fields each factor needs besides ``close``
FACTOR_FIELDS = {
    "net_active_buy": ("buy_amount", "sell_amount", "amount"),
    "momentum": (),
    "reversal": (),
    "turnover": ("amount", "float_mv"),
}


def _share(values: np.ndarray) -> np.ndarray:
    """Each sector's share of the day's total (NaN where the sector has no value)."""
    total = np.nansum(values, axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(total > 0, values / total, np.nan)


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Simple moving average down the rows; NaN until ``window`` valid days are available."""
    window = max(int(window), 1)
    valid = ~np.isnan(values)
    csum = np.cumsum(np.where(valid, values, 0.0), axis=0)
    count = np.cumsum(valid, axis=0)
    out = np.full(values.shape, np.nan)
    if len(values) >= window:
        total = csum[window - 1:] - np.vstack([np.zeros((1, values.shape[1])), csum[:-window]])
        full = (count[window - 1:] - np.vstack([np.zeros((1, values.shape[1]), dtype=count.dtype), count[:-window]])) == window
        out[window - 1:] = np.where(full, total / window, np.nan)
    return out


def factor_values(name: str, panel: dict[str, np.ndarray], window: int) -> np.ndarray:
    """(days x sectors) factor matrix; larger is better. Uses data up to and including each day."""
    close = panel["close"]
    if name == "net_active_buy":
        # shares of the whole market cancel the systematic gap between "active buy" and "active sell" totals
        net = _share(panel["buy_amount"]) - _share(panel["sell_amount"])
        with np.errstate(invalid="ignore", divide="ignore"):
            raw = net / _share(panel["amount"])
        return rolling_mean(raw, window)
    if name in ("momentum", "reversal"):
        out = np.full(close.shape, np.nan)
        if len(close) > window:
            with np.errstate(invalid="ignore", divide="ignore"):
                out[window:] = close[window:] / close[:-window] - 1
        return out if name == "momentum" else -out
    if name == "turnover":
        with np.errstate(invalid="ignore", divide="ignore"):
            return rolling_mean(panel["amount"] / panel["float_mv"], window)
    raise ValueError(f"unknown factor {name}")


def period_ends(days: list[str], frequency: str) -> list[int]:
    """Indexes of the last trading day of each week / month (the still-open last period is dropped)."""
    def key(day: str) -> tuple[int, int]:
        d = date.fromisoformat(day)
        return tuple(d.isocalendar()[:2]) if frequency == "weekly" else (d.year, d.month)

    return [i for i in range(len(days) - 1) if key(days[i]) != key(days[i + 1])]


def performance(nav: np.ndarray) -> dict[str, float | None]:
    if len(nav) < 2:
        return {"total_return": 0.0, "annualized_return": None, "volatility": None, "sharpe": None,
                "max_drawdown": 0.0, "calmar": None}
    returns = nav[1:] / nav[:-1] - 1
    years = (len(nav) - 1) / TRADING_DAYS
    annual = float((nav[-1] / nav[0]) ** (1 / years) - 1) if years > 0 else None
    vol = float(np.std(returns, ddof=1) * np.sqrt(TRADING_DAYS)) if len(returns) > 1 else None
    drawdown = float(np.min(nav / np.maximum.accumulate(nav) - 1))
    return {
        "total_return": round(float(nav[-1] / nav[0] - 1), 6),
        "annualized_return": None if annual is None else round(annual, 6),
        "volatility": None if vol is None else round(vol, 6),
        "sharpe": round(annual / vol, 4) if annual is not None and vol else None,
        "max_drawdown": round(drawdown, 6),
        "calmar": round(annual / abs(drawdown), 4) if annual is not None and drawdown < 0 else None,
    }


def yearly_returns(days: list[str], nav: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {}
    start = nav[0]
    for i in range(1, len(days)):
        if i == len(days) - 1 or days[i][:4] != days[i + 1][:4]:
            out[days[i][:4]] = round(float(nav[i] / start - 1), 6)
            start = nav[i]
    return out


def run_rotation(days: list[str], codes: list[str], panel: dict[str, np.ndarray], *, factor: str, window: int,
                 top_n: int = 5, frequency: str = "weekly", fee_rate: float = 0.0, start: str | None = None,
                 end: str | None = None) -> dict[str, Any]:
    """Backtest one factor / window. ``panel`` holds full history (for warm-up); the curve starts at ``start``."""
    close = panel["close"]
    with np.errstate(invalid="ignore", divide="ignore"):
        returns = np.vstack([np.zeros((1, close.shape[1])), close[1:] / close[:-1] - 1])
    returns = np.where(np.isnan(returns), 0.0, returns)
    listed = ~np.isnan(close)
    scores = factor_values(factor, panel, window)

    first = next((i for i, d in enumerate(days) if start is None or d >= start), len(days))
    last = max((i for i, d in enumerate(days) if end is None or d <= end), default=-1)
    if last - first < 1:
        raise ValueError("回测区间里的交易日太少")
    signal_at = {i + 1: i for i in period_ends(days, frequency)}  # rebalance day -> signal day

    weights = np.zeros(len(codes))
    nav, bench = [1.0], [1.0]
    value, bench_value = 1.0, 1.0
    rebalances: list[dict[str, Any]] = []
    turnover_total = 0.0
    for i in range(first + 1, last + 1):
        day_return = float(weights @ returns[i])
        value *= 1 + day_return
        if weights.any():  # weights drift with prices until the next rebalance
            weights = weights * (1 + returns[i]) / (1 + day_return)
        members = listed[i] & listed[i - 1]
        bench_value *= 1 + (float(returns[i][members].mean()) if members.any() else 0.0)
        signal = signal_at.get(i)
        if signal is not None and signal >= first:
            row = scores[signal]
            ranked = [j for j in np.argsort(-np.where(np.isnan(row), -np.inf, row)) if not np.isnan(row[j]) and listed[i][j]]
            picks = ranked[:top_n]
            if picks:
                target = np.zeros(len(codes))
                target[picks] = 1 / len(picks)
                change = target - weights
                turnover = float(change[change > 0].sum())  # share of the portfolio bought
                value *= 1 - float(np.abs(change).sum()) * fee_rate  # fee on everything sold and bought
                turnover_total += turnover
                weights = target
                rebalances.append({"signal_date": days[signal], "trade_date": days[i],
                                   "holdings": [{"code": codes[j], "score": round(float(row[j]), 6)} for j in picks],
                                   "turnover": round(turnover, 4)})
        nav.append(value)
        bench.append(bench_value)

    curve_days = days[first:last + 1]
    nav_arr, bench_arr = np.array(nav), np.array(bench)
    metrics, bench_metrics = performance(nav_arr), performance(bench_arr)
    years, bench_years = yearly_returns(curve_days, nav_arr), yearly_returns(curve_days, bench_arr)
    return {
        "factor": factor, "window": window, "top_n": top_n, "frequency": frequency,
        "days": curve_days,
        "nav": [round(float(v), 6) for v in nav_arr],
        "benchmark_nav": [round(float(v), 6) for v in bench_arr],
        "metrics": {**metrics, "excess_annualized": None if metrics["annualized_return"] is None or bench_metrics["annualized_return"] is None
                    else round(metrics["annualized_return"] - bench_metrics["annualized_return"], 6),
                    "rebalances": len(rebalances),
                    "avg_turnover": round(turnover_total / len(rebalances), 4) if rebalances else None},
        "benchmark_metrics": bench_metrics,
        "yearly": [{"year": y, "strategy": years[y], "benchmark": bench_years.get(y),
                    "excess": None if bench_years.get(y) is None else round(years[y] - bench_years[y], 6)} for y in years],
        "rebalances": rebalances,
    }

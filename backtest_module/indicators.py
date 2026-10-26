"""Vectorised-in-spirit indicator helpers. Every function is O(n) over the input list.

``IndicatorCache`` computes each distinct expression once per backtest; the previous engine
recomputed the whole series on every bar (O(n^2)).
"""
from __future__ import annotations

import json
import math
from collections import deque
from typing import Any, Sequence


Series = list[float | None]


def moving_average(values: Sequence[float], period: int) -> Series:
    period = max(int(period), 1)
    out: Series = []
    window_sum = 0.0
    for index, value in enumerate(values):
        window_sum += value
        if index >= period:
            window_sum -= values[index - period]
        out.append(window_sum / period if index + 1 >= period else None)
    return out


def exponential_moving_average(values: Sequence[float], period: int) -> Series:
    """EMA seeded with the simple average of the first ``period`` values."""
    period = max(int(period), 1)
    multiplier = 2 / (period + 1)
    out: Series = []
    ema: float | None = None
    running = 0.0
    for index, value in enumerate(values):
        if ema is None:
            running += value
            if index + 1 < period:
                out.append(None)
                continue
            ema = running / period
        else:
            ema = value * multiplier + ema * (1 - multiplier)
        out.append(ema)
    return out


def _ema_of_optional(values: Series, period: int) -> Series:
    """EMA over a series whose head is None (used for the MACD signal line)."""
    start = next((i for i, v in enumerate(values) if v is not None), None)
    if start is None:
        return [None] * len(values)
    tail = exponential_moving_average([float(v) for v in values[start:]], period)  # type: ignore[arg-type]
    return [None] * start + tail


def rsi(values: Sequence[float], period: int) -> Series:
    """RSI using the simple average of gains/losses over the last ``period`` changes (Cutler)."""
    period = max(int(period), 1)
    out: Series = [None]
    gains: list[float] = []
    losses: list[float] = []
    gain_sum = loss_sum = 0.0
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        gain, loss = max(delta, 0.0), max(-delta, 0.0)
        gains.append(gain)
        losses.append(loss)
        gain_sum += gain
        loss_sum += loss
        if len(gains) > period:
            gain_sum -= gains[-period - 1]
            loss_sum -= losses[-period - 1]
        if len(gains) < period:
            out.append(None)
            continue
        if loss_sum <= 1e-12:
            out.append(100.0)
        else:
            rs = gain_sum / loss_sum
            out.append(100 - 100 / (1 + rs))
    return out


def period_return(values: Sequence[float], period: int) -> Series:
    period = max(int(period), 1)
    out: Series = []
    for index, value in enumerate(values):
        base = values[index - period] if index >= period else 0
        out.append(value / base - 1 if index >= period and base else None)
    return out


def prior_extreme(values: Sequence[float], period: int, highest: bool) -> Series:
    """Highest (or lowest) value of the previous ``period`` bars, not counting the current bar,
    so "close above the 20-day high" can be true on a breakout day (Donchian / Turtle channels)."""
    period = max(int(period), 1)
    window: deque[int] = deque()  # indexes with monotonic values; the front is the extreme
    out: Series = []
    for index, value in enumerate(values):
        while window and window[0] < index - period:
            window.popleft()
        out.append(values[window[0]] if index >= period else None)
        while window and (values[window[-1]] <= value if highest else values[window[-1]] >= value):
            window.pop()
        window.append(index)
    return out


def rolling_std(values: Sequence[float | None], period: int) -> Series:
    """Population standard deviation over a rolling window (None until the window is full)."""
    period = max(int(period), 1)
    out: Series = []
    s = s2 = 0.0
    count = 0
    for index, value in enumerate(values):
        v = 0.0 if value is None else float(value)
        s += v
        s2 += v * v
        count += 1
        if index >= period:
            old = values[index - period]
            o = 0.0 if old is None else float(old)
            s -= o
            s2 -= o * o
            count -= 1
        if index + 1 < period:
            out.append(None)
            continue
        mean = s / period
        out.append(math.sqrt(max(s2 / period - mean * mean, 0.0)))
    return out


def volatility(values: Sequence[float], period: int) -> Series:
    returns: list[float] = [0.0]
    for index in range(1, len(values)):
        prev = values[index - 1]
        returns.append(values[index] / prev - 1 if prev else 0.0)
    return rolling_std(returns, period)


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Series]:
    fast_ema = exponential_moving_average(values, fast)
    slow_ema = exponential_moving_average(values, slow)
    line: Series = [None if a is None or b is None else a - b for a, b in zip(fast_ema, slow_ema)]
    signal_line = _ema_of_optional(line, signal)
    hist: Series = [None if a is None or b is None else a - b for a, b in zip(line, signal_line)]
    return {"macd": line, "signal": signal_line, "hist": hist}


def bollinger(values: Sequence[float], period: int = 20, num_std: float = 2.0) -> dict[str, Series]:
    middle = moving_average(values, period)
    std = rolling_std(values, period)
    upper: Series = [None if m is None or s is None else m + num_std * s for m, s in zip(middle, std)]
    lower: Series = [None if m is None or s is None else m - num_std * s for m, s in zip(middle, std)]
    return {"upper": upper, "middle": middle, "lower": lower}


class IndicatorCache:
    """Evaluates DSL expressions over a fixed set of price series, memoising by expression."""

    def __init__(self, series: dict[str, list[float]]):
        self.series = series
        self.length = len(next(iter(series.values()), []))
        self._memo: dict[str, Series] = {}
        self._by_id: dict[int, tuple[dict[str, Any], Series]] = {}

    # Backwards compatibility: the old cache was a plain dict of series.
    def __getitem__(self, key: str) -> list[float]:
        return self.series[key]

    def values(self, expr: dict[str, Any]) -> Series:
        hit = self._by_id.get(id(expr))
        if hit is not None and hit[0] is expr:
            return hit[1]
        key = json.dumps(expr, sort_keys=True, ensure_ascii=False)
        if key not in self._memo:
            self._memo[key] = self._compute(expr)
        self._by_id[id(expr)] = (expr, self._memo[key])
        return self._memo[key]

    def _compute(self, expr: dict[str, Any]) -> Series:
        expr_type = expr.get("type")
        if expr_type == "price":
            return list(self.series[expr["field"]])
        if expr_type == "constant":
            return [float(expr["value"])] * self.length
        if expr_type != "indicator":
            raise ValueError(f"unsupported expression: {expr}")
        name = expr["name"]
        params = expr.get("params", {}) or {}
        field = params.get("field", "close")
        values = self.series[field]
        period = int(params.get("period", 14))
        if name == "MA":
            return moving_average(values, period)
        if name == "EMA":
            return exponential_moving_average(values, period)
        if name == "RSI":
            return rsi(values, period)
        if name == "VOLUME_MA":
            return moving_average(self.series["volume"], period)
        if name == "RETURN":
            return period_return(values, period)
        if name == "VOLATILITY":
            return volatility(values, period)
        if name in ("HIGHEST", "LOWEST"):
            return prior_extreme(values, period, highest=name == "HIGHEST")
        if name == "MACD":
            result = macd(values, int(params.get("fast", 12)), int(params.get("slow", 26)), int(params.get("signal", 9)))
            return result[params.get("output", "macd")]
        if name == "BOLL":
            result = bollinger(values, int(params.get("period", 20)), float(params.get("std", 2.0)))
            return result[params.get("output", "middle")]
        raise ValueError(f"unsupported indicator: {name}")

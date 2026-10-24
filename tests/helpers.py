"""Synthetic bars for engine tests (clearly not market data)."""
from __future__ import annotations

import math
from datetime import date, timedelta

from backtest_engine import Bar


def weekdays(start: str, count: int) -> list[str]:
    day = date.fromisoformat(start)
    out = []
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def make_bars(symbol: str, closes: list[float], start: str = "2024-01-02", volume: float = 1_000_000,
              factors: list[float] | None = None, opens: list[float] | None = None) -> list[Bar]:
    days = weekdays(start, len(closes))
    bars = []
    for i, (day, close) in enumerate(zip(days, closes)):
        open_ = opens[i] if opens else (closes[i - 1] if i else close)
        bars.append(Bar(symbol, "1d", day, open_, max(open_, close) * 1.001, min(open_, close) * 0.999, close,
                        volume, volume * close, factors[i] if factors else 1.0))
    return bars


def wave(n: int, base: float = 100.0, amp: float = 10.0, period: int = 40) -> list[float]:
    return [round(base + amp * math.sin(2 * math.pi * i / period), 2) for i in range(n)]


def strategy(symbol: str, market: str, entry: dict, exit_: dict, start: str, end: str, cash: float = 1_000_000,
             size: float = 1.0, execution: dict | None = None, risk: dict | None = None, adjustment: str = "none") -> dict:
    return {
        "schema_version": "1.0", "strategy_id": "t", "name": "t", "market": market,
        "universe": {"type": "single", "symbols": [symbol]},
        "data": {"frequency": "1d", "adjustment": adjustment, "start_date": start, "end_date": end},
        "entry": entry, "exit": exit_,
        "position": {"initial_cash": cash, "order_size_type": "cash_pct", "order_size_value": size, "max_position_pct": size},
        "execution": execution or {"entry_price": "next_open", "exit_price": "next_open", "slippage_rate": 0},
        "risk": risk or {"stop_loss_pct": None, "take_profit_pct": None, "max_drawdown_pct": None, "max_holding_bars": None},
    }


def gt(value: float) -> dict:
    return {"logic": "all", "conditions": [{"left": {"type": "price", "field": "close"}, "operator": "gt",
                                           "right": {"type": "constant", "value": value}}]}


def lt(value: float) -> dict:
    return {"logic": "any", "conditions": [{"left": {"type": "price", "field": "close"}, "operator": "lt",
                                           "right": {"type": "constant", "value": value}}]}

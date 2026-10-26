"""Single-symbol, bar-by-bar backtest engine for A-shares, HK stocks and 港股通 (Southbound Connect).

What it models (all driven by market_rules_module/configs/market_rules.json):

* Lots: A-share 100-share lots (STAR: 200 minimum, then 1-share steps; BSE: 100 then 1),
  HK board lots per stock (instruments.lot_size > config board_lots > default 100, with a warning).
* T+1 for A-shares (shares bought today cannot be sold until the next trading day); T+0 for HK/港股通.
* Daily price limits by board for A-shares: no buy fill at limit-up, no sell fill at limit-down.
  HK has no daily limit. Bars with zero volume are treated as suspended (no fills).
* Fees by component (commission with minimum, stamp duty, transfer/levy/trading/settlement fees)
  with date-dependent schedules, e.g. A-share sell stamp duty 0.1% -> 0.05% on 2023-08-28.
* 港股通: HKD prices, CNY account; HKD->CNY rate per day from the fx_rates table (else the
  configured default, with a warning); trades only on days both HK and mainland are open.
* Dividends and bonus shares from corporate_actions (or derived from adj_factor jumps), with
  withholding tax (A-share holding-period tiers settled at sale; 港股通 20% at payment by default).
* Signals on forward/backward-adjusted or raw prices; fills always at raw (actually traded) prices.
* Indicator warm-up history before start_date; pending next-open orders; exits retry until filled.
* Metrics annualised by calendar time (CAGR) and by bars-per-year for the market/frequency (Sharpe).

Not modelled: intraday price paths, partial fills / volume caps, auction rules, HK VCM/CAS,
borrowing/shorting, multi-symbol portfolios.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from indicators import IndicatorCache  # noqa: E402
from market_rules_module import market_rules as mr  # noqa: E402
from market_rules_module import trading_calendar  # noqa: E402


FREQUENCY_MINUTES = {"1d": None, "60m": 60, "30m": 30, "15m": 15}
MIN_DAYS_FOR_CAGR = 60
MAX_LOGGED_BLOCKED_ORDERS = 200


# --------------------------------------------------------------------------- data classes


@dataclass
class Bar:
    symbol: str
    frequency: str
    trade_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    adj_factor: float = 1.0  # forward-adjust factor: adjusted price = raw price * adj_factor


@dataclass
class CorporateAction:
    ex_date: str
    cash_dividend: float = 0.0  # per share, in the quote currency
    bonus_ratio: float = 0.0  # new shares per existing share (10送5 -> 0.5)
    source: str = "corporate_actions"


@dataclass
class InstrumentInfo:
    symbol: str
    name: str | None = None
    lot_size: int | None = None
    connect_eligible: bool | None = None


@dataclass
class MarketContext:
    instrument: InstrumentInfo | None = None
    corporate_actions: list[CorporateAction] | None = None  # None = unknown, derive from adj_factor
    fx_rates: dict[str, float] = field(default_factory=dict)  # 'YYYY-MM-DD' -> quote->account rate
    rules: dict[str, Any] | None = None


@dataclass
class Trade:
    symbol: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl: float
    net_pnl: float
    return_pct: float
    entry_fee: float
    exit_fee: float
    exit_reason: str
    holding_bars: int
    entry_quantity: int = 0
    dividends_net: float = 0.0
    dividend_tax: float = 0.0
    entry_fx: float = 1.0
    exit_fx: float = 1.0


@dataclass
class EquityPoint:
    trade_time: str
    cash: float
    position_qty: int
    close: float
    equity: float
    drawdown_pct: float


# --------------------------------------------------------------------------- loading


def load_strategy(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def end_bound(end_date: str) -> str:
    """Inclusive upper bound that also covers intraday bars on the end date."""
    return end_date if len(end_date) > 10 else f"{end_date} 23:59:59"


def required_warmup_bars(strategy: dict[str, Any]) -> int:
    """Longest indicator lookback used by the entry/exit rules (+1 for cross detection)."""
    longest = 0

    def visit(expr: dict[str, Any] | None) -> None:
        nonlocal longest
        if not isinstance(expr, dict) or expr.get("type") != "indicator":
            return
        params = expr.get("params", {}) or {}
        name = expr.get("name")
        if name == "MACD":
            need = int(params.get("slow", 26)) + int(params.get("signal", 9))
        elif name == "BOLL":
            need = int(params.get("period", 20))
        else:
            need = int(params.get("period", 14)) + (1 if name in {"RSI", "RETURN", "VOLATILITY", "HIGHEST", "LOWEST"} else 0)
        longest = max(longest, need)

    for group_name in ("entry", "exit"):
        for condition in (strategy.get(group_name) or {}).get("conditions", []):
            visit(condition.get("left"))
            visit(condition.get("right"))
            longest = max(longest, int(condition.get("lookback_bars") or 0))
    return longest + 1 if longest else 0


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def load_bars(db_path: Path, strategy: dict[str, Any], warmup_bars: int | None = None) -> list[Bar]:
    """Bars for the strategy window plus ``warmup_bars`` earlier bars for indicator history."""
    symbol = mr.normalize_symbol(strategy["universe"]["symbols"][0])
    frequency = strategy["data"]["frequency"]
    start = strategy["data"]["start_date"]
    end = end_bound(strategy["data"]["end_date"])
    warmup = required_warmup_bars(strategy) if warmup_bars is None else warmup_bars
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        adj = "adj_factor" if "adj_factor" in _columns(conn, "bars") else "1.0 AS adj_factor"
        select = f"SELECT symbol, frequency, trade_time, open, high, low, close, volume, amount, {adj} FROM bars"
        rows = conn.execute(
            f"{select} WHERE symbol = ? AND frequency = ? AND trade_time >= ? AND trade_time <= ? ORDER BY trade_time",
            (symbol, frequency, start, end),
        ).fetchall()
        history = []
        if warmup:
            history = conn.execute(
                f"{select} WHERE symbol = ? AND frequency = ? AND trade_time < ? ORDER BY trade_time DESC LIMIT ?",
                (symbol, frequency, start, warmup),
            ).fetchall()
    return [Bar(**dict(row)) for row in reversed(history)] + [Bar(**dict(row)) for row in rows]


def load_market_context(db_path: Path, strategy: dict[str, Any]) -> MarketContext:
    """Instrument metadata, corporate actions and FX rates from the research SQLite database."""
    symbol = mr.normalize_symbol(strategy["universe"]["symbols"][0])
    context = MarketContext()
    if not Path(db_path).exists():
        return context
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if _table_exists(conn, "instruments"):
            cols = _columns(conn, "instruments")
            row = conn.execute("SELECT * FROM instruments WHERE symbol = ?", (symbol,)).fetchone()
            if row is not None:
                context.instrument = InstrumentInfo(
                    symbol=symbol,
                    name=row["name"],
                    lot_size=row["lot_size"] if "lot_size" in cols else None,
                    connect_eligible=(None if "connect_eligible" not in cols or row["connect_eligible"] is None
                                      else bool(row["connect_eligible"])),
                )
        if _table_exists(conn, "corporate_actions"):
            rows = conn.execute(
                "SELECT ex_date, cash_dividend, bonus_ratio, source FROM corporate_actions WHERE symbol = ? ORDER BY ex_date",
                (symbol,),
            ).fetchall()
            if rows:
                chosen: dict[str, list[sqlite3.Row]] = {}
                for r in rows:  # explicit (csv/manual) actions win over feed-derived ones on the same ex-date
                    bucket = chosen.setdefault(r["ex_date"], [])
                    derived = (r["source"] or "").endswith("_derived")
                    if bucket and (bucket[0]["source"] or "").endswith("_derived") and not derived:
                        bucket.clear()
                    if not bucket or derived == (bucket[0]["source"] or "").endswith("_derived"):
                        bucket.append(r)
                context.corporate_actions = [
                    CorporateAction(r["ex_date"], float(r["cash_dividend"] or 0), float(r["bonus_ratio"] or 0), r["source"] or "db")
                    for day in sorted(chosen) for r in chosen[day]
                ]
        if _table_exists(conn, "fx_rates"):
            pair = "HKDCNY"
            for r in conn.execute("SELECT rate_date, rate FROM fx_rates WHERE pair = ? ORDER BY rate_date", (pair,)):
                context.fx_rates[str(r["rate_date"])[:10]] = float(r["rate"])
    return context


# --------------------------------------------------------------------------- rule evaluation


def build_series_cache(bars: list[Bar], adjustment: str = "none", base_index: int = 0) -> IndicatorCache:
    """Price series used for signals. Volume is raw.

    forward  : raw * adj_factor (latest bar = raw). Levels before later dividends are shifted down,
               so absolute price thresholds see future corporate actions — prefer 'none' or
               'backward' for constant thresholds; ratios (MA cross, RSI, returns) are unaffected.
    backward : rebased so the first bar of the backtest window equals its raw price.
    none     : raw traded prices.
    """
    factors = [bar.adj_factor or 1.0 for bar in bars]
    if adjustment == "backward" and factors:
        base = factors[min(base_index, len(factors) - 1)]
        factors = [f / base for f in factors]
    elif adjustment not in {"forward", "backward"}:
        factors = [1.0] * len(bars)
    return IndicatorCache(
        {
            "open": [bar.open * f for bar, f in zip(bars, factors)],
            "high": [bar.high * f for bar, f in zip(bars, factors)],
            "low": [bar.low * f for bar, f in zip(bars, factors)],
            "close": [bar.close * f for bar, f in zip(bars, factors)],
            "volume": [bar.volume for bar in bars],
            "amount": [bar.amount for bar in bars],
        }
    )


def _as_cache(cache: Any, bars: list[Bar]) -> IndicatorCache:
    if isinstance(cache, IndicatorCache):
        return cache
    if isinstance(cache, dict):
        return IndicatorCache(cache)
    return build_series_cache(bars)


def expression_values(expr: dict[str, Any], bars: list[Bar], cache: Any) -> list[float | None]:
    return _as_cache(cache, bars).values(expr)


def compare(left: float, right: float, operator: str) -> bool:
    if operator == "gt":
        return left > right
    if operator == "lt":
        return left < right
    if operator == "eq":
        return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)
    if operator == "gte":
        return left >= right
    if operator == "lte":
        return left <= right
    raise ValueError(f"operator requires cross evaluation: {operator}")


def _condition_at(condition: dict[str, Any], index: int, cache: IndicatorCache) -> bool:
    left_values = cache.values(condition["left"])
    right_values = cache.values(condition["right"])
    left, right = left_values[index], right_values[index]
    if left is None or right is None:
        return False
    operator = condition["operator"]
    if operator in {"cross_above", "cross_below"}:
        if index == 0:
            return False
        prev_left, prev_right = left_values[index - 1], right_values[index - 1]
        if prev_left is None or prev_right is None:
            return False
        if operator == "cross_above":
            return prev_left <= prev_right and left > right
        return prev_left >= prev_right and left < right
    return compare(float(left), float(right), operator)


def condition_met(condition: dict[str, Any], index: int, bars: list[Bar], cache: Any) -> bool:
    """True when the condition holds on this bar (or on any of the last ``lookback_bars`` bars)."""
    cache = _as_cache(cache, bars)
    lookback = int(condition.get("lookback_bars") or 1)
    return any(_condition_at(condition, i, cache) for i in range(index, max(index - lookback, -1), -1))


def rule_group_met(group: dict[str, Any], index: int, bars: list[Bar], cache: Any) -> bool:
    cache = _as_cache(cache, bars)
    values = [condition_met(condition, index, bars, cache) for condition in group["conditions"]]
    return all(values) if group["logic"] == "all" else any(values)


def execution_price(mode: str, bars: list[Bar], index: int, side: str, slippage_rate: float) -> tuple[float, int] | None:
    """Legacy helper (used by the paper trader): raw fill price and bar index, with slippage."""
    exec_index = index
    if mode == "next_open":
        exec_index = index + 1
        if exec_index >= len(bars):
            return None
        raw_price = bars[exec_index].open
    elif mode == "current_close":
        raw_price = bars[exec_index].close
    else:
        raise ValueError(f"unsupported execution price mode: {mode}")
    if side == "buy":
        return raw_price * (1 + slippage_rate), exec_index
    return raw_price * (1 - slippage_rate), exec_index


# --------------------------------------------------------------------------- helpers


def derive_corporate_actions(bars: list[Bar]) -> list[CorporateAction]:
    """Infer ex-dates from adj_factor jumps between consecutive daily bars.

    ratio = f[t-1] / f[t] = (P - D) / (P * (1 + B)). Ratios below 0.8 are treated as bonus/split
    shares, otherwise as a cash dividend D = P * (1 - ratio). Mixed cash+bonus events are
    approximated; import explicit corporate_actions for exact dividend tax.
    """
    actions: list[CorporateAction] = []
    last_date = None
    prev_close = prev_factor = None
    for bar in bars:
        day = bar.trade_time[:10]
        factor = bar.adj_factor or 1.0
        if day != last_date and prev_factor is not None and prev_close:
            ratio = prev_factor / factor
            if ratio < 0.9999:
                if ratio < 0.8:
                    actions.append(CorporateAction(day, 0.0, round(1 / ratio - 1, 6), "derived_adj_factor"))
                else:
                    actions.append(CorporateAction(day, round(prev_close * (1 - ratio), 6), 0.0, "derived_adj_factor"))
        prev_close, prev_factor, last_date = bar.close, factor, day
    return actions


def periods_per_year(rule: dict[str, Any], frequency: str) -> float:
    days = float(rule.get("trading_days_per_year", 242))
    minutes = FREQUENCY_MINUTES.get(frequency)
    if minutes is None:
        return days
    return days * float(rule.get("session_minutes", 240)) / minutes


def _parse_date(text: str) -> date:
    return date.fromisoformat(text[:10])


# --------------------------------------------------------------------------- engine


def run_backtest(strategy: dict[str, Any], bars: list[Bar], context: MarketContext | None = None) -> dict[str, Any]:
    if not bars:
        raise ValueError("no bars available for backtest")
    context = context or MarketContext()
    rules = context.rules or mr.load_rules()
    symbol = mr.normalize_symbol(strategy["universe"]["symbols"][0])
    requested_market = mr.normalize_market(strategy.get("market"))
    market, rule = mr.get_market_rule(rules, symbol, requested_market)
    if market is None or rule is None:
        raise ValueError(f"symbol {symbol} cannot be traded in market {strategy.get('market')}")

    warnings: list[str] = []
    data_cfg = strategy.get("data", {})
    if data_cfg.get("end_date"):
        upper = end_bound(data_cfg["end_date"])
        bars = [bar for bar in bars if bar.trade_time <= upper]
        if not bars:
            raise ValueError("no bars available inside the backtest window")
    frequency = data_cfg.get("frequency", bars[0].frequency)
    start_date = data_cfg.get("start_date", bars[0].trade_time[:10])
    adjustment = data_cfg.get("adjustment", "forward")
    start_index = next((i for i, bar in enumerate(bars) if bar.trade_time[:10] >= start_date), None)
    if start_index is None:
        raise ValueError("no bars available inside the backtest window")
    if start_index == 0 and required_warmup_bars(strategy) > 1:
        warnings.append("no indicator warm-up history before start_date; early signals may be missing")

    instrument = context.instrument or InstrumentInfo(symbol=symbol)
    lot = mr.lot_rule(rule, symbol, instrument.lot_size)
    if lot.lot_source == "default":
        warnings.append(
            f"board lot for {symbol} unknown; using default {lot.lot_size}. Run data_module/fetch_market_data.py --board-lots"
        )

    currency = rule.get("currency", "CNY")
    quote_currency = rule.get("quote_currency", currency)
    fx_cfg = rule.get("fx", {})
    execution = strategy.get("execution", {})
    fx_override = execution.get("fx_rate")
    fx_spread = float(execution.get("fx_spread", fx_cfg.get("spread", 0.0)) or 0.0)
    fx_series = {day: rate for day, rate in (context.fx_rates or {}).items() if rate and rate > 0}
    if fx_override is not None and float(fx_override) <= 0:
        raise ValueError("execution.fx_rate must be positive")
    fx_dates = sorted(fx_series)
    fx_state = {"default_used": False}

    def fx_rate(day: str) -> float:
        """Quote->account currency rate on ``day`` (last known rate, back-filled at the start)."""
        if quote_currency == currency:
            return 1.0
        if fx_override:
            return float(fx_override)
        if fx_dates:
            pos = bisect.bisect_right(fx_dates, day) - 1
            return float(fx_series[fx_dates[max(pos, 0)]])
        fx_state["default_used"] = True
        return float(fx_cfg.get("default_rate", 1.0))

    # 港股通 can only trade when both HK and the mainland are open.
    tradable_days: frozenset[date] | None = None
    if market == "hk_connect":
        tradable_days, source = trading_calendar.trading_days(
            market, _parse_date(bars[start_index].trade_time), _parse_date(bars[-1].trade_time)
        )
        if source != "exchange_calendars":
            warnings.append("exchange_calendars not installed; 港股通 holiday closures are not modelled")
        eligible = mr.is_connect_eligible(rule, symbol, instrument.connect_eligible)
        if eligible is None:
            warnings.append("港股通 eligibility not configured for this symbol; assumed eligible")
        elif eligible is False:
            warnings.append(f"{symbol} is not eligible for 港股通; buy orders are blocked")

    actions = context.corporate_actions
    if actions is None:
        actions = derive_corporate_actions(bars) if any(abs((b.adj_factor or 1) - (bars[0].adj_factor or 1)) > 1e-9 for b in bars) else []
        if actions:
            warnings.append("dividends/bonus shares derived from adj_factor jumps (approximate)")
    actions = sorted(actions, key=lambda a: a.ex_date)
    action_pos = 0
    while action_pos < len(actions) and actions[action_pos].ex_date <= bars[start_index].trade_time[:10]:
        action_pos += 1  # actions before the first traded bar do not affect an empty account

    volume_known = any(bar.volume > 0 for bar in bars)
    if not volume_known:
        warnings.append("no volume in the data; suspensions cannot be detected")
    cache = build_series_cache(bars, adjustment, base_index=start_index)
    signal_close = cache["close"]
    total_return_index = [bar.close * (bar.adj_factor or 1.0) for bar in bars]  # forward-adjusted

    initial_cash = float(strategy["position"]["initial_cash"])
    order_size_value = float(strategy["position"]["order_size_value"])
    max_position_pct = float(strategy["position"]["max_position_pct"])
    entry_mode = execution.get("entry_price", "next_open")
    exit_mode = execution.get("exit_price", "next_open")
    if "current_close" in (entry_mode, exit_mode):
        warnings.append("current_close execution fills at the signal bar's close (assumes a closing-auction order)")
    slippage_rate = float(execution.get("slippage_rate", 0) or 0)
    fee_overrides = {
        "commission_rate": execution.get("commission_rate", execution.get("fee_rate")),
        "brokerage_rate": execution.get("commission_rate", execution.get("fee_rate")) if market == "hk_stock" else None,
        "min_commission": execution.get("min_commission"),
        "min_brokerage": execution.get("min_commission") if market == "hk_stock" else None,
    }
    risk = strategy.get("risk", {})

    cash = initial_cash
    qty = 0
    entry: dict[str, Any] = {}
    pending_entry = False
    pending_exit: str | None = None
    halted = False
    peak_equity = initial_cash
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []
    blocked: list[dict[str, Any]] = []
    blocked_counts: dict[str, int] = {}
    total_fees = 0.0
    dividends_net_total = 0.0
    dividend_tax_total = 0.0
    bars_in_market = 0

    prev_day: str | None = None
    prev_day_close: float | None = None
    prev_day_factor = 1.0
    if start_index > 0:  # warm-up bar gives the first day's price-limit reference
        prev_day_close = bars[start_index - 1].close
        prev_day_factor = bars[start_index - 1].adj_factor or 1.0
    limit_down = limit_up = None

    def block(index: int, side: str, reason: str) -> None:
        blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
        if len(blocked) < MAX_LOGGED_BLOCKED_ORDERS:
            blocked.append({"trade_time": bars[index].trade_time, "side": side, "reason": reason})

    def tradable(index: int) -> bool:
        bar = bars[index]
        if volume_known and bar.volume <= 0:  # zero volume = suspended, when the feed reports volume
            return False
        return tradable_days is None or _parse_date(bar.trade_time) in tradable_days

    def try_buy(index: int, raw_price: float) -> bool:
        nonlocal cash, qty, entry, total_fees
        bar = bars[index]
        day = bar.trade_time[:10]
        if not tradable(index):
            block(index, "buy", "suspended_or_market_closed")
            return False
        if limit_up is not None and raw_price >= limit_up - 1e-9:
            block(index, "buy", "limit_up")
            return False
        if market == "hk_connect" and mr.is_connect_eligible(rule, symbol, instrument.connect_eligible) is False:
            block(index, "buy", "not_connect_eligible")
            return False
        price = raw_price * (1 + slippage_rate)
        if limit_up is not None:
            price = min(price, limit_up)
        fx = fx_rate(day) * (1 + fx_spread)
        equity_now = cash
        budget = min(cash * order_size_value, equity_now * max_position_pct)
        fee_rate = mr.estimated_fee_rate(rules, symbol, "buy", market, day, fee_overrides)
        quantity = mr.round_buy_quantity(lot, budget / (price * fx * (1 + fee_rate)))
        while quantity > 0:
            fee = mr.calculate_fee_breakdown(rules, symbol, "buy", quantity * price, market, day, fee_overrides).total_fee * fx
            cost = quantity * price * fx + fee
            if cost <= cash + 1e-9:
                cash -= cost
                qty = quantity
                total_fees += fee
                entry = {
                    "time": bar.trade_time, "day": day, "index": index, "price": price, "fx": fx,
                    "qty": quantity, "fee": fee, "cost": cost, "adj_price": price * (bar.adj_factor or 1.0),
                    "div_gross": 0.0, "div_tax_paid": 0.0,
                }
                return True
            quantity = mr.round_buy_quantity(lot, quantity - lot.buy_step)
        block(index, "buy", "insufficient_cash_for_one_lot")
        return False

    def try_sell(index: int, raw_price: float, reason: str) -> bool:
        nonlocal cash, qty, entry, total_fees, dividends_net_total, dividend_tax_total
        bar = bars[index]
        day = bar.trade_time[:10]
        if not tradable(index):
            block(index, "sell", "suspended_or_market_closed")
            return False
        if rule.get("t_plus_one") and day <= entry["day"]:
            block(index, "sell", "t_plus_one")
            return False
        if limit_down is not None and raw_price <= limit_down + 1e-9:
            block(index, "sell", "limit_down")
            return False
        price = raw_price * (1 - slippage_rate)
        if limit_down is not None:
            price = max(price, limit_down)
        fx = fx_rate(day) * (1 - fx_spread)
        fee = mr.calculate_fee_breakdown(rules, symbol, "sell", qty * price, market, day, fee_overrides).total_fee * fx
        proceeds = qty * price * fx - fee
        holding_days = (_parse_date(day) - _parse_date(entry["day"])).days
        deferred_tax = 0.0
        if rule.get("dividend_tax", {}).get("mode") == "holding_period" and entry["div_gross"]:
            deferred_tax = entry["div_gross"] * mr.dividend_tax_rate(rule, symbol, holding_days)
        cash += proceeds - deferred_tax
        total_fees += fee
        dividend_tax = entry["div_tax_paid"] + deferred_tax
        dividends_net = entry["div_gross"] - dividend_tax
        dividend_tax_total += deferred_tax
        dividends_net_total -= deferred_tax
        gross_pnl = qty * price * fx - entry["qty"] * entry["price"] * entry["fx"]
        net_pnl = proceeds - entry["cost"] + dividends_net
        trades.append(
            Trade(
                symbol=symbol,
                entry_time=entry["time"],
                exit_time=bar.trade_time,
                entry_price=round(entry["price"], 6),
                exit_price=round(price, 6),
                quantity=qty,
                gross_pnl=round(gross_pnl, 6),
                net_pnl=round(net_pnl, 6),
                return_pct=round(net_pnl / entry["cost"], 6) if entry["cost"] else 0.0,
                entry_fee=round(entry["fee"], 6),
                exit_fee=round(fee, 6),
                exit_reason=reason,
                holding_bars=index - entry["index"] + 1,
                entry_quantity=entry["qty"],
                dividends_net=round(dividends_net, 6),
                dividend_tax=round(dividend_tax, 6),
                entry_fx=round(entry["fx"], 6),
                exit_fx=round(fx, 6),
            )
        )
        qty = 0
        entry = {}
        return True

    for index in range(start_index, len(bars)):
        bar = bars[index]
        day = bar.trade_time[:10]
        factor = bar.adj_factor or 1.0
        new_day = day != prev_day

        if new_day:
            # Corporate actions take effect before the first bar of the ex-date.
            todays_cash = todays_bonus = 0.0
            while action_pos < len(actions) and actions[action_pos].ex_date <= day:
                action = actions[action_pos]
                todays_cash += action.cash_dividend
                todays_bonus += action.bonus_ratio
                if qty > 0:
                    if action.cash_dividend:
                        gross = qty * action.cash_dividend * fx_rate(day)
                        tax_now = 0.0
                        if rule.get("dividend_tax", {}).get("mode") != "holding_period":
                            tax_now = gross * mr.dividend_tax_rate(rule, symbol)
                        cash += gross - tax_now
                        entry["div_gross"] += gross
                        entry["div_tax_paid"] += tax_now
                        dividends_net_total += gross - tax_now
                        dividend_tax_total += tax_now
                    if action.bonus_ratio:
                        qty += int(math.floor(qty * action.bonus_ratio + 1e-9))
                action_pos += 1
            # Daily price limits are relative to the (ex-rights) previous close.
            pct = mr.price_limit_pct(rule, symbol, instrument.name, day)
            if pct is not None and prev_day_close:
                if todays_cash or todays_bonus:
                    reference = (prev_day_close - todays_cash) / (1 + todays_bonus)
                else:
                    reference = prev_day_close * prev_day_factor / factor
                limit_down, limit_up = mr.limit_prices(reference, pct)
            else:
                limit_down = limit_up = None

        # 1) Orders queued on the previous bar fill at this bar's open.
        if pending_exit and qty > 0 and exit_mode == "next_open":
            if try_sell(index, bar.open, pending_exit):
                pending_exit = None
        if pending_entry and qty == 0 and not halted and not pending_exit:
            try_buy(index, bar.open)
        pending_entry = False

        # 2) Mark to market and evaluate risk at the close.
        fx_close = fx_rate(day)
        equity = cash + qty * bar.close * fx_close
        peak_equity = max(peak_equity, equity)
        drawdown_pct = 0.0 if peak_equity <= 0 else (peak_equity - equity) / peak_equity

        if qty > 0:
            exit_reason = pending_exit
            if exit_reason is None:
                gross_return = bar.close * factor / entry["adj_price"] - 1 if entry.get("adj_price") else 0.0
                if rule_group_met(strategy["exit"], index, bars, cache):
                    exit_reason = "exit_rule"
                elif risk.get("stop_loss_pct") is not None and gross_return <= -float(risk["stop_loss_pct"]):
                    exit_reason = "stop_loss"
                elif risk.get("take_profit_pct") is not None and gross_return >= float(risk["take_profit_pct"]):
                    exit_reason = "take_profit"
                elif risk.get("max_holding_bars") is not None and index - entry["index"] + 1 >= int(risk["max_holding_bars"]):
                    exit_reason = "max_holding_bars"
            if risk.get("max_drawdown_pct") is not None and drawdown_pct >= float(risk["max_drawdown_pct"]):
                halted = True
                exit_reason = exit_reason or "max_drawdown_stop"
            if exit_reason:
                if exit_mode == "current_close":
                    pending_exit = None if try_sell(index, bar.close, exit_reason) else exit_reason
                else:
                    pending_exit = exit_reason
        elif risk.get("max_drawdown_pct") is not None and drawdown_pct >= float(risk["max_drawdown_pct"]):
            halted = True

        # 3) Entry signal.
        if not halted and qty == 0 and not pending_exit and rule_group_met(strategy["entry"], index, bars, cache):
            if entry_mode == "current_close":
                try_buy(index, bar.close)
            elif index + 1 < len(bars):
                pending_entry = True

        if qty > 0:
            bars_in_market += 1
        mark_equity = cash + qty * bar.close * fx_close
        peak_equity = max(peak_equity, mark_equity)
        drawdown_pct = 0.0 if peak_equity <= 0 else (peak_equity - mark_equity) / peak_equity
        equity_curve.append(
            EquityPoint(
                trade_time=bar.trade_time,
                cash=round(cash, 6),
                position_qty=qty,
                close=bar.close,
                equity=round(mark_equity, 6),
                drawdown_pct=round(drawdown_pct, 6),
            )
        )
        # Track the last close of each trading day (raw) for the next day's limit reference.
        if index + 1 >= len(bars) or bars[index + 1].trade_time[:10] != day:
            prev_day_close = bar.close
            prev_day_factor = factor
        prev_day = day

    if fx_state["default_used"]:
        warnings.append(
            f"no {fx_cfg.get('pair', 'FX')} rates loaded; used default rate {fx_cfg.get('default_rate')} for every day"
        )

    traded_bars = bars[start_index:]
    final_equity = equity_curve[-1].equity
    first_day, last_day = traded_bars[0].trade_time[:10], traded_bars[-1].trade_time[:10]
    benchmark = None
    if total_return_index[start_index] > 0:
        benchmark = (total_return_index[-1] * fx_rate(last_day)) / (total_return_index[start_index] * fx_rate(first_day)) - 1
    metrics = calculate_metrics(
        initial_cash, final_equity, trades, equity_curve, traded_bars,
        periods=periods_per_year(rule, frequency),
    )
    metrics.update(
        {
            "total_fees": round(total_fees, 6),
            "dividends_net": round(dividends_net_total, 6),
            "dividend_tax": round(dividend_tax_total, 6),
            "benchmark_return": round(benchmark, 6) if benchmark is not None else None,
            "excess_return": round(metrics["total_return"] - benchmark, 6) if benchmark is not None else None,
            "exposure_pct": round(bars_in_market / len(traded_bars), 6),
            "blocked_orders": dict(sorted(blocked_counts.items())),
            "currency": currency,
        }
    )
    if metrics.get("annualized_return") is None:
        warnings.append(f"sample shorter than {MIN_DAYS_FOR_CAGR} calendar days; annualized_return not reported")
    if len(traded_bars) < 120:
        warnings.append(f"only {len(traded_bars)} bars in the backtest window; results are not statistically meaningful")

    open_position = None
    if qty > 0:
        last = traded_bars[-1]
        open_position = {
            "entry_time": entry["time"],
            "quantity": qty,
            "entry_price": round(entry["price"], 6),
            "last_close": last.close,
            "market_value": round(qty * last.close * fx_rate(last_day), 6),
            "unrealized_pnl": round(qty * last.close * fx_rate(last_day) - entry["cost"] + entry["div_gross"] - entry["div_tax_paid"], 6),
        }

    return {
        "strategy_id": strategy["strategy_id"],
        "strategy_name": strategy["name"],
        "symbol": symbol,
        "market": market,
        "currency": currency,
        "quote_currency": quote_currency,
        "frequency": frequency,
        "start_date": data_cfg.get("start_date"),
        "end_date": data_cfg.get("end_date"),
        "adjustment": adjustment,
        "lot_size": lot.lot_size,
        "lot_source": lot.lot_source,
        "metrics": metrics,
        "warnings": warnings,
        "trades": [asdict(trade) for trade in trades],
        "open_position": open_position,
        "blocked_orders": blocked,
        "equity_curve": [asdict(point) for point in equity_curve],
    }


def calculate_metrics(
    initial_cash: float,
    final_equity: float,
    trades: list[Trade],
    equity_curve: list[EquityPoint],
    bars: list[Bar],
    periods: float = 242,
) -> dict[str, Any]:
    total_return = final_equity / initial_cash - 1
    max_drawdown = max((point.drawdown_pct for point in equity_curve), default=0)
    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl < 0]
    win_rate = len(wins) / len(trades) if trades else 0
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = abs(sum(trade.net_pnl for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else None
    total_fees = sum(trade.entry_fee + trade.exit_fee for trade in trades)
    average_holding_bars = sum(trade.holding_bars for trade in trades) / len(trades) if trades else 0

    annualized_return = None
    calendar_days = 0
    if bars:
        calendar_days = (_parse_date(bars[-1].trade_time) - _parse_date(bars[0].trade_time)).days
        if calendar_days >= MIN_DAYS_FOR_CAGR:
            annualized_return = (final_equity / initial_cash) ** (365.25 / calendar_days) - 1 if final_equity > 0 else -1.0

    equity_returns = []
    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1].equity
        current = equity_curve[index].equity
        equity_returns.append(current / previous - 1 if previous else 0)
    sharpe = calculate_sharpe(equity_returns, periods)
    return {
        "initial_cash": round(initial_cash, 6),
        "final_equity": round(final_equity, 6),
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized_return, 6) if annualized_return is not None else None,
        "max_drawdown": round(max_drawdown, 6),
        "win_rate": round(win_rate, 6),
        "profit_factor": round(profit_factor, 6) if profit_factor is not None else None,
        "trade_count": len(trades),
        "average_holding_bars": round(average_holding_bars, 6),
        "total_fees": round(total_fees, 6),
        "sharpe": round(sharpe, 6) if sharpe is not None else None,
        "bar_count": len(bars),
        "calendar_days": calendar_days,
        "periods_per_year": round(periods, 4),
    }


def calculate_sharpe(returns: list[float], annual_factor: float) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    return mean / std * math.sqrt(annual_factor)


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "trades.csv", report["trades"])
    write_csv(output_dir / "equity_curve.csv", report["equity_curve"])


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AQuant backtest (A-share / HK / 港股通)")
    parser.add_argument("strategy_path")
    parser.add_argument("--db", default="data_module/market_data.sqlite")
    parser.add_argument("--output-dir", default="backtest_module/output/latest")
    args = parser.parse_args()

    strategy = load_strategy(Path(args.strategy_path))
    bars = load_bars(Path(args.db), strategy)
    context = load_market_context(Path(args.db), strategy)
    report = run_backtest(strategy, bars, context)
    write_report(report, Path(args.output_dir))
    print(json.dumps({"ok": True, "output_dir": args.output_dir, "metrics": report["metrics"], "warnings": report["warnings"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

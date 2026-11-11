"""Daily signals (which stocks trigger a strategy's buy/sell rules on the latest close) and
paper accounts (virtual money following a strategy forward, filled by the backtest engine's rules)."""
from __future__ import annotations

import copy
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MarketBar, MarketInstrument, PaperAccount
from app.services.backtest_service import batch_market, batch_strategy
from app.services.market_data_access import load_engine_bars, load_engine_context
from app.services.strategy_service import validate_strategy_payload

from backtest_engine import Bar, build_series_cache, condition_met, required_warmup_bars, rule_group_met, run_backtest  # noqa: E402

MAX_SCAN = 300
MAX_PAPER_SYMBOLS = 20


def _names(db: Session, symbols: list[str]) -> dict[str, str]:
    return {i.symbol: i.name for i in db.scalars(select(MarketInstrument).where(MarketInstrument.symbol.in_(symbols)))}


def _last_days(db: Session, symbols: list[str], frequency: str) -> dict[str, str]:
    rows = db.execute(select(MarketBar.symbol, func.max(MarketBar.trade_time))
                      .where(MarketBar.symbol.in_(symbols), MarketBar.frequency == frequency)
                      .group_by(MarketBar.symbol))
    return {symbol: last for symbol, last in rows}


def _group_detail(group: dict[str, Any], index: int, bars: list, cache: Any) -> list[dict[str, Any]]:
    out = []
    for condition in group.get("conditions", []):
        left, right = cache.values(condition["left"])[index], cache.values(condition["right"])[index]
        out.append({"left_value": None if left is None else round(float(left), 4),
                    "right_value": None if right is None else round(float(right), 4),
                    "met": condition_met(condition, index, bars, cache)})
    return out


def evaluate_last_bar(strategy: dict[str, Any], bars: list) -> dict[str, Any]:
    """Whether the entry / exit rules hold on the last bar, with each condition's values."""
    index = len(bars) - 1
    cache = build_series_cache(bars, strategy.get("data", {}).get("adjustment", "forward"))
    return {
        "entry": rule_group_met(strategy["entry"], index, bars, cache),
        "exit": rule_group_met(strategy["exit"], index, bars, cache),
        "entry_conditions": _group_detail(strategy["entry"], index, bars, cache),
        "exit_conditions": _group_detail(strategy["exit"], index, bars, cache),
    }


def with_live_bar(bars: list, quote: dict[str, Any] | None) -> tuple[list, bool]:
    """Today's bar built from a live quote: replaces a stored bar of the same day or is appended.
    Rules then read the current price as if it were the close (盘中预判)."""
    if not bars or not quote or not quote.get("traded") or not quote.get("time"):
        return bars, False
    day, last = quote["time"][:10], bars[-1]
    if day < last.trade_time[:10]:
        return bars, False
    price = float(quote["price"])
    live = Bar(last.symbol, last.frequency, day, float(quote.get("open") or price), float(quote.get("high") or price),
               float(quote.get("low") or price), price, float(quote.get("volume") or 0), float(quote.get("amount") or 0),
               last.adj_factor)
    return (bars[:-1] if day == last.trade_time[:10] else bars) + [live], True


def scan_signals(db: Session, strategies: list[dict[str, Any]], symbols: list[str],
                 quotes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Every strategy x stock on that stock's latest bar. Strategies are {strategy_id, name, strategy}.
    With ``quotes`` (live prices), daily strategies are judged on today's price as if it were the close."""
    names = _names(db, symbols)
    rows: list[dict[str, Any]] = []
    for item in strategies:
        strategy = item["strategy"]
        frequency = strategy.get("data", {}).get("frequency", "1d")
        last = _last_days(db, symbols, frequency)
        for symbol in symbols:
            row: dict[str, Any] = {"symbol": symbol, "name": names.get(symbol, symbol), "strategy_id": item.get("strategy_id"),
                                   "strategy_name": item.get("name") or strategy.get("name"), "date": None, "close": None,
                                   "change": None, "signal": None, "error": None}
            if symbol not in last:
                row["error"] = "没有行情，先到「行情数据」同步"
                rows.append(row)
                continue
            day = last[symbol][:10]
            run = batch_strategy(strategy, symbol, day, day)
            bars = load_engine_bars(db, run, warmup_bars=required_warmup_bars(run) + 5)
            if not bars:
                row["error"] = "没有行情"
                rows.append(row)
                continue
            live = False
            if quotes is not None and frequency == "1d":
                bars, live = with_live_bar(bars, quotes.get(symbol))
            result = evaluate_last_bar(run, bars)
            signal = "buy" if result["entry"] and not result["exit"] else "sell" if result["exit"] and not result["entry"] \
                else "both" if result["entry"] else None
            previous = bars[-2].close if len(bars) > 1 else None
            row.update(date=bars[-1].trade_time, close=bars[-1].close, signal=signal, market=run["market"], live=live,
                       change=round(bars[-1].close / previous - 1, 6) if previous else None,
                       entry_conditions=result["entry_conditions"], exit_conditions=result["exit_conditions"])
            rows.append(row)
    latest = max((r["date"][:10] for r in rows if r["date"]), default=None)
    for row in rows:  # flag stocks whose data stops well before the freshest stock in the scan
        row["stale"] = bool(row["date"] and latest and (date.fromisoformat(latest) - date.fromisoformat(row["date"][:10])).days > 4)
    return {"rows": rows, "latest_date": latest,
            "buy": sum(1 for r in rows if r["signal"] in ("buy", "both")),
            "sell": sum(1 for r in rows if r["signal"] in ("sell", "both"))}


# --------------------------------------------------------------------------- paper accounts

class PaperInputError(ValueError):
    pass


def create_paper_account(db: Session, owner_id: int, name: str, strategy: dict[str, Any], source_strategy_id: str | None,
                         symbols: list[str], initial_cash: float, start_date: str) -> PaperAccount:
    check = validate_strategy_payload(strategy)
    if not check["ok"]:
        raise PaperInputError("策略不完整：" + "；".join(check["errors"]))
    market = str(strategy.get("market", "a_share"))
    wrong = [s for s in symbols if batch_market(market, s) != market]
    if wrong:
        raise PaperInputError(f"{'、'.join(wrong)} 和策略的市场不一致（一个模拟盘只用一种货币），请分开建")
    account = PaperAccount(account_id=f"pa_{uuid4().hex[:12]}", owner_id=owner_id, name=name.strip(),
                           source_strategy_id=source_strategy_id, strategy_json=copy.deepcopy(strategy),
                           symbols_json=symbols, initial_cash=initial_cash, start_date=start_date)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _pending_order(strategy: dict[str, Any], bars: list, open_position: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the account would do at the next open, judged on the latest close."""
    if not bars:
        return None
    result = evaluate_last_bar(strategy, bars)
    if open_position is None:
        return {"side": "buy", "reason": "买入信号"} if result["entry"] else None
    if result["exit"]:
        return {"side": "sell", "reason": "卖出信号"}
    risk = strategy.get("risk") or {}
    change = bars[-1].close / open_position["entry_price"] - 1 if open_position.get("entry_price") else 0
    if risk.get("stop_loss_pct") is not None and change <= -float(risk["stop_loss_pct"]):
        return {"side": "sell", "reason": "止损"}
    if risk.get("take_profit_pct") is not None and change >= float(risk["take_profit_pct"]):
        return {"side": "sell", "reason": "止盈"}
    return None


def evaluate_paper_account(db: Session, account: PaperAccount, today: str | None = None) -> dict[str, Any]:
    """Replay the strategy from the start date to the latest bar, one equal cash sleeve per stock."""
    today = today or date.today().isoformat()
    symbols: list[str] = list(account.symbols_json)
    sleeve_cash = account.initial_cash / max(1, len(symbols))
    names = _names(db, symbols)
    sleeves, trades, positions, pending = [], [], [], []
    curves: dict[str, dict[str, dict[str, float]]] = {}
    currency = None
    for symbol in symbols:
        run = batch_strategy(account.strategy_json, symbol, account.start_date, today)
        run["position"] = dict(run.get("position") or {}, initial_cash=sleeve_cash)
        sleeve: dict[str, Any] = {"symbol": symbol, "name": names.get(symbol, symbol), "status": "waiting",
                                  "last_date": None, "equity": sleeve_cash, "total_return": 0.0, "hold_return": None}
        bars = load_engine_bars(db, run)
        if not any(bar.trade_time[:10] >= account.start_date for bar in bars):
            sleeves.append(sleeve)  # no bar since the start yet: the sleeve is still all cash
            continue
        try:
            report = run_backtest(run, bars, load_engine_context(db, run))
        except ValueError as exc:
            sleeve.update(status="error", error=str(exc))
            sleeves.append(sleeve)
            continue
        currency = currency or report.get("currency")
        metrics = report["metrics"]
        sleeve.update(status="ok", last_date=bars[-1].trade_time[:10], equity=metrics["final_equity"],
                      total_return=metrics["total_return"], hold_return=metrics.get("benchmark_return"))
        sleeves.append(sleeve)
        curves[symbol] = {p["trade_time"][:10]: p for p in report["equity_curve"]}
        for trade in report["trades"]:
            trades.append({**trade, "symbol": symbol, "name": sleeve["name"]})
        position = report.get("open_position")
        if position:
            positions.append({**position, "symbol": symbol, "name": sleeve["name"],
                              "return_pct": position["last_close"] / position["entry_price"] - 1 if position["entry_price"] else None})
        order = _pending_order(run, bars, position)
        if order:
            pending.append({**order, "symbol": symbol, "name": sleeve["name"], "date": bars[-1].trade_time[:10],
                            "close": bars[-1].close})

    days = sorted({d for curve in curves.values() for d in curve})
    curve, peak = [], account.initial_cash
    carried = {s: {"equity": sleeve_cash, "cash": sleeve_cash} for s in symbols}
    for day in days:
        for symbol, points in curves.items():
            if day in points:
                carried[symbol] = {"equity": points[day]["equity"], "cash": points[day]["cash"]}
        equity = sum(v["equity"] for v in carried.values())
        peak = max(peak, equity)
        curve.append({"trade_time": day, "equity": round(equity, 2), "cash": round(sum(v["cash"] for v in carried.values()), 2),
                      "drawdown_pct": round((peak - equity) / peak, 6) if peak else 0.0, "position_qty": 0, "close": None})
    equity = curve[-1]["equity"] if curve else account.initial_cash
    holds = [s["hold_return"] for s in sleeves if s["hold_return"] is not None]
    trades.sort(key=lambda t: t["exit_time"], reverse=True)
    return {
        "account_id": account.account_id,
        "name": account.name,
        "strategy_name": account.strategy_json.get("name"),
        "source_strategy_id": account.source_strategy_id,
        "market": account.strategy_json.get("market"),
        "currency": currency or ("HKD" if account.strategy_json.get("market") == "hk_stock" else "CNY"),
        "symbols": symbols,
        "initial_cash": account.initial_cash,
        "start_date": account.start_date,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "summary": {
            "equity": equity,
            "total_return": round(equity / account.initial_cash - 1, 6),
            "cash": curve[-1]["cash"] if curve else account.initial_cash,
            "day_change": round(curve[-1]["equity"] / curve[-2]["equity"] - 1, 6) if len(curve) > 1 else None,
            "hold_return": round(sum(holds) / len(holds), 6) if holds else None,
            "max_drawdown": max((p["drawdown_pct"] for p in curve), default=0.0),
            "last_date": days[-1] if days else None,
            "positions": len(positions),
            "trades": len(trades),
        },
        "curve": curve,
        "positions": positions,
        "pending": pending,
        "trades": trades,
        "sleeves": sleeves,
    }


def list_paper_accounts(db: Session, owner_id: int) -> list[PaperAccount]:
    return list(db.scalars(select(PaperAccount).where(PaperAccount.owner_id == owner_id)
                           .order_by(PaperAccount.created_at.desc())))


def get_paper_account(db: Session, owner_id: int, account_id: str) -> PaperAccount | None:
    account = db.get(PaperAccount, account_id)
    return account if account is not None and account.owner_id == owner_id else None

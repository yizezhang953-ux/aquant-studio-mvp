from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BacktestEquityPoint, BacktestRun, BacktestTrade, MarketInstrument, StrategyVersion
from app.services.market_data_access import available_data, load_engine_bars, load_engine_context
from app.services.strategy_service import validate_strategy_payload

from backtest_engine import run_backtest  # noqa: E402  (path set up by market_data_access)


class BacktestInputError(ValueError):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


def no_data_message(db: Session, strategy: dict[str, Any]) -> str:
    """Explain, in the UI's language, why there is nothing to backtest and what to change."""
    symbol = str(strategy["universe"]["symbols"][0]).strip().upper()
    frequency = strategy["data"]["frequency"]
    start, end = strategy["data"]["start_date"], strategy["data"]["end_date"]
    held = available_data(db, limit=50)
    same_symbol = [d for d in held if d["symbol"] == symbol]
    parts = [f"没有 {symbol} 的 {frequency} 行情（回测区间 {start} 至 {end}）。"]
    exact = next((d for d in same_symbol if d["frequency"] == frequency), None)
    if exact:
        parts.append(f"已有数据在 {exact['start']} 至 {exact['end']}，请把策略的开始/结束日期调到这个范围内。")
    elif same_symbol:
        other = "、".join(f"{d['frequency']}（{d['start']} 至 {d['end']}）" for d in same_symbol)
        parts.append(f"这只股票已有：{other}。请把策略编辑器里的「周期」改成 {same_symbol[0]['frequency']}，保存后再回测。")
    else:
        parts.append(f"请先到「行情数据」→「同步真实日线」同步 {symbol}，或把策略的「代码」改成已有数据的股票。")
        real = [d for d in held if d["bars"] > 20]
        if real:
            parts.append("已有：" + "、".join(f"{d['symbol']} {d['frequency']}（{d['start']} 至 {d['end']}）"
                                           for d in real[:5]) + "。")
    if frequency != "1d" and not exact:
        parts.append("腾讯行情只能同步日线（1d），分钟线只能用 CSV 导入。")
    return "".join(parts)


def run_backtest_payload(db: Session, strategy: dict[str, Any]) -> dict[str, Any]:
    """Validate, then backtest against the web database's market data. Returns the full report."""
    validation = validate_strategy_payload(strategy)
    if not validation["ok"]:
        raise BacktestInputError("strategy is invalid", validation["errors"])
    bars = load_engine_bars(db, strategy)
    if not any(bar.trade_time[:10] >= strategy["data"]["start_date"] for bar in bars):
        raise BacktestInputError(no_data_message(db, strategy))
    try:
        report = run_backtest(strategy, bars, load_engine_context(db, strategy))
    except ValueError as exc:
        raise BacktestInputError(str(exc)) from exc
    report["backtest_id"] = f"bt_{uuid4().hex[:12]}"
    report["strategy"] = strategy
    return report


MARKET_NAMES = {"a_share": "A股", "hk_stock": "港股", "hk_connect": "港股通"}
NAME_SUFFIX = re.compile(r"\s*-\s*我的策略$")


def _month(day: str | None) -> str:
    return day[:7].replace("-", ".") if day else "?"


def default_backtest_name(market: str | None, strategy_name: str, stock_name: str | None, symbol: str,
                          start_date: str | None, end_date: str | None) -> str:
    """e.g. 港股 RSI 回调策略 百胜中国 2021.01-2025.12"""
    label = MARKET_NAMES.get(market or "", "")
    strategy = NAME_SUFFIX.sub("", strategy_name.strip())
    for prefix in ("港股通", "港股", "A股"):
        if strategy.startswith(prefix):
            strategy = strategy[len(prefix):].strip()
            break
    if not strategy.endswith("策略"):
        strategy += "策略"
    parts = [label, strategy, stock_name or symbol, f"{_month(start_date)}-{_month(end_date)}"]
    return " ".join(part for part in parts if part)[:200]


def backtest_name(db: Session, run: BacktestRun, stock_names: dict[str, str] | None = None) -> str:
    """The user's own name for a run, or the generated one for runs never renamed."""
    if run.display_name:
        return run.display_name
    if stock_names is None:
        instrument = db.get(MarketInstrument, run.symbol)
        stock_names = {run.symbol: instrument.name} if instrument else {}
    market = (run.report_json or {}).get("market")
    return default_backtest_name(market, run.strategy_name, stock_names.get(run.symbol), run.symbol,
                                 run.start_date, run.end_date)


def rename_user_backtest(db: Session, owner_id: int, backtest_id: str, name: str | None) -> BacktestRun | None:
    """Empty name goes back to the generated one."""
    run = db.get(BacktestRun, backtest_id)
    if run is None or run.owner_id != owner_id:
        return None
    run.display_name = (name or "").strip()[:200] or None
    db.commit()
    return run


def persist_backtest_report(
    db: Session,
    backtest_id: str,
    report: dict[str, Any],
    owner_id: int | None = None,
    source_strategy_id: str | None = None,
) -> BacktestRun:
    run = db.get(BacktestRun, backtest_id)
    strategy_version = get_latest_strategy_version(db, source_strategy_id)
    parameter_snapshot = build_parameter_snapshot(report)
    instrument = db.get(MarketInstrument, report["symbol"])
    payload = {
        "backtest_id": backtest_id,
        "owner_id": owner_id,
        "strategy_id": report["strategy_id"],
        "source_strategy_id": source_strategy_id,
        "strategy_version": strategy_version,
        "strategy_name": report["strategy_name"],
        "display_name": default_backtest_name(report.get("market"), report["strategy_name"],
                                              instrument.name if instrument else None, report["symbol"],
                                              report.get("start_date"), report.get("end_date")),
        "symbol": report["symbol"],
        "frequency": report["frequency"],
        "status": "completed",
        "start_date": report.get("start_date"),
        "end_date": report.get("end_date"),
        "metrics_json": report.get("metrics", {}),
        "report_json": report,
        "parameter_snapshot": parameter_snapshot,
    }
    if run is None:
        run = BacktestRun(**payload)
        db.add(run)
    else:
        for key, value in payload.items():
            setattr(run, key, value)
        run.trades.clear()
        run.equity_points.clear()

    for trade in report.get("trades", []):
        run.trades.append(
            BacktestTrade(
                symbol=trade["symbol"],
                entry_time=trade["entry_time"],
                exit_time=trade["exit_time"],
                entry_price=trade["entry_price"],
                exit_price=trade["exit_price"],
                quantity=trade["quantity"],
                gross_pnl=trade["gross_pnl"],
                net_pnl=trade["net_pnl"],
                return_pct=trade["return_pct"],
                exit_reason=trade["exit_reason"],
            )
        )

    for point in report.get("equity_curve", []):
        run.equity_points.append(
            BacktestEquityPoint(
                trade_time=point["trade_time"],
                cash=point["cash"],
                position_qty=point["position_qty"],
                close=point["close"],
                equity=point["equity"],
                drawdown_pct=point["drawdown_pct"],
            )
        )
    db.commit()
    db.refresh(run)
    return run


def get_latest_strategy_version(db: Session, source_strategy_id: str | None) -> int | None:
    if source_strategy_id is None:
        return None
    return db.scalar(
        select(func.max(StrategyVersion.version)).where(
            StrategyVersion.strategy_id == source_strategy_id
        )
    )


def build_parameter_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    strategy = report.get("strategy") or {}
    # Older reports may not embed strategy; fall back to report-level fields.
    data = strategy.get("data", {})
    universe = strategy.get("universe", {})
    entry = (strategy.get("entry", {}).get("conditions") or [{}])[0]
    exit_rule = (strategy.get("exit", {}).get("conditions") or [{}])[0]
    position = strategy.get("position", {})
    risk = strategy.get("risk", {})
    return {
        "symbol": (universe.get("symbols") or [report.get("symbol")])[0],
        "frequency": data.get("frequency", report.get("frequency")),
        "start_date": data.get("start_date", report.get("start_date")),
        "end_date": data.get("end_date", report.get("end_date")),
        "entry_operator": entry.get("operator"),
        "entry_value": entry.get("right", {}).get("value"),
        "exit_operator": exit_rule.get("operator"),
        "exit_value": exit_rule.get("right", {}).get("value"),
        "order_size_value": position.get("order_size_value"),
        "max_position_pct": position.get("max_position_pct"),
        "stop_loss_pct": risk.get("stop_loss_pct"),
        "take_profit_pct": risk.get("take_profit_pct"),
        "max_drawdown_pct": risk.get("max_drawdown_pct"),
    }


def list_user_backtests(db: Session, owner_id: int) -> list[BacktestRun]:
    return list(
        db.scalars(
            select(BacktestRun)
            .where(BacktestRun.owner_id == owner_id)
            .order_by(BacktestRun.created_at.desc())
        ).all()
    )


def delete_user_backtests(db: Session, owner_id: int, backtest_ids: list[str]) -> int:
    """Delete the user's own runs (with their trades and equity points); seeded demo runs are left alone."""
    runs = db.scalars(
        select(BacktestRun).where(BacktestRun.owner_id == owner_id, BacktestRun.backtest_id.in_(backtest_ids))
    ).all()
    for run in runs:
        db.delete(run)
    db.commit()
    return len(runs)


def get_user_backtest(db: Session, owner_id: int, backtest_id: str) -> BacktestRun | None:
    """A run owned by the user (seeded demo runs with no owner are readable by everyone)."""
    run = db.get(BacktestRun, backtest_id)
    if run is None or (run.owner_id is not None and run.owner_id != owner_id):
        return None
    return run

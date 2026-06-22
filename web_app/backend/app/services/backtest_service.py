from __future__ import annotations

import sys
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BacktestEquityPoint, BacktestRun, BacktestTrade, StrategyVersion
from app.services.json_utils import read_json, write_json
from app.services.legacy_paths import BACKTEST_MODULE, DATA_MODULE, REPO_ROOT


sys.path.insert(0, str(BACKTEST_MODULE))

from backtest_engine import load_bars, run_backtest, write_report  # noqa: E402


DEFAULT_DB_PATH = DATA_MODULE / "market_data.sqlite"
RUNTIME_DIR = REPO_ROOT / "web_app" / "backend" / "runtime" / "backtests"


def run_backtest_payload(strategy: dict[str, Any]) -> dict[str, Any]:
    backtest_id = f"bt_{uuid4().hex[:12]}"
    output_dir = RUNTIME_DIR / backtest_id
    bars = load_bars(DEFAULT_DB_PATH, strategy)
    report = run_backtest(strategy, bars)
    report["backtest_id"] = backtest_id
    report["strategy"] = strategy
    write_report(report, output_dir)
    write_json(output_dir / "strategy.json", strategy)
    return {
        "backtest_id": backtest_id,
        "status": "completed",
        "metrics": report["metrics"],
        "report_path": str(output_dir / "report.json"),
    }


def get_backtest_report(backtest_id: str) -> dict[str, Any] | None:
    report_path = RUNTIME_DIR / backtest_id / "report.json"
    if not report_path.exists():
        return None
    return read_json(report_path)


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
    payload = {
        "backtest_id": backtest_id,
        "owner_id": owner_id,
        "strategy_id": report["strategy_id"],
        "source_strategy_id": source_strategy_id,
        "strategy_version": strategy_version,
        "strategy_name": report["strategy_name"],
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


def get_user_backtest(db: Session, owner_id: int, backtest_id: str) -> BacktestRun | None:
    return db.scalar(
        select(BacktestRun).where(
            BacktestRun.owner_id == owner_id,
            BacktestRun.backtest_id == backtest_id,
        )
    )

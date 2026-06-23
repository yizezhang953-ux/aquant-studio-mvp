from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.db.session import Base, engine
from app.models import (
    AuditLog,
    BacktestEquityPoint,
    BacktestRun,
    BacktestTrade,
    MarketBar,
    MarketInstrument,
    StrategyVersion,
    StrategyTemplate,
    User,
    UserSession,
    UserStrategy,
)
from app.services.json_utils import read_json
from app.services.legacy_paths import BACKTEST_MODULE, DATA_MODULE, TEMPLATE_MODULE


TABLE_MODELS = {
    "users": User,
    "user_sessions": UserSession,
    "strategy_templates": StrategyTemplate,
    "user_strategies": UserStrategy,
    "strategy_versions": StrategyVersion,
    "market_instruments": MarketInstrument,
    "market_bars": MarketBar,
    "backtest_runs": BacktestRun,
    "backtest_trades": BacktestTrade,
    "backtest_equity_points": BacktestEquityPoint,
    "audit_logs": AuditLog,
}


def create_database() -> None:
    Base.metadata.create_all(bind=engine)
    _upgrade_sqlite_schema()


def get_database_status(db: Session) -> dict[str, Any]:
    create_database()
    counts = {
        table_name: db.scalar(select(func.count()).select_from(model)) or 0
        for table_name, model in TABLE_MODELS.items()
    }
    return {
        "database": "ready",
        "dialect": engine.dialect.name,
        "table_count": len(TABLE_MODELS),
        "tables": counts,
    }


def initialize_database(db: Session, seed: bool = True) -> dict[str, Any]:
    create_database()
    seeded: dict[str, int] = {}
    if seed:
        seeded["strategy_templates"] = seed_strategy_templates(db)
        seeded["user_strategies"] = seed_user_strategies(db)
        seeded["strategy_versions"] = seed_strategy_versions(db)
        market_counts = seed_market_data(db)
        seeded.update(market_counts)
        backtest_counts = seed_backtest_demo(db)
        seeded.update(backtest_counts)
        db.add(
            AuditLog(
                event_type="database_initialized",
                status="completed",
                message="Database schema created and seed data synchronized.",
                payload_json=seeded,
            )
        )
        db.commit()
    status = get_database_status(db)
    status["seeded"] = seeded
    return status


def seed_strategy_templates(db: Session) -> int:
    template_index = read_json(TEMPLATE_MODULE / "templates" / "index.json")
    inserted_or_updated = 0
    for item in template_index.get("templates", []):
        strategy_json = read_json(TEMPLATE_MODULE / "templates" / item["file"])
        template = db.scalar(
            select(StrategyTemplate).where(StrategyTemplate.template_id == item["template_id"])
        )
        payload = {
            "template_id": item["template_id"],
            "name": item["name"],
            "market": template_index.get("market", "a_share"),
            "category": item["category"],
            "risk_level": item["risk_level"],
            "default_symbol": item["default_symbol"],
            "default_frequency": item["default_frequency"],
            "description": item.get("description", ""),
            "strategy_json": strategy_json,
        }
        if template is None:
            db.add(StrategyTemplate(**payload))
        else:
            for key, value in payload.items():
                setattr(template, key, value)
        inserted_or_updated += 1
    db.commit()
    return inserted_or_updated


def seed_user_strategies(db: Session) -> int:
    templates = db.scalars(select(StrategyTemplate)).all()
    changed = 0
    for template in templates:
        strategy_json = template.strategy_json
        strategy_id = strategy_json.get("strategy_id") or f"seed_{template.template_id}"
        strategy = db.scalar(select(UserStrategy).where(UserStrategy.strategy_id == strategy_id))
        symbols = strategy_json.get("universe", {}).get("symbols") or [template.default_symbol]
        payload = {
            "strategy_id": strategy_id,
            "owner_id": None,
            "name": strategy_json.get("name", template.name),
            "market": strategy_json.get("market", template.market),
            "symbol": symbols[0],
            "frequency": strategy_json.get("data", {}).get("frequency", template.default_frequency),
            "source_template_id": template.template_id,
            "status": "draft",
            "strategy_json": strategy_json,
        }
        if strategy is None:
            db.add(UserStrategy(**payload))
        else:
            for key, value in payload.items():
                setattr(strategy, key, value)
        changed += 1
    db.commit()
    return changed


def seed_market_data(db: Session) -> dict[str, int]:
    source_db = DATA_MODULE / "market_data.sqlite"
    if not source_db.exists():
        return {"market_instruments": 0, "market_bars": 0}

    inserted_instruments = 0
    inserted_bars = 0
    with _legacy_connection(source_db) as conn:
        for row in conn.execute("select * from instruments"):
            symbol = row["symbol"]
            instrument = db.get(MarketInstrument, symbol)
            payload = {
                "symbol": symbol,
                "name": row["name"],
                "market": row["market"],
                "exchange": row["exchange"],
                "asset_type": row["asset_type"],
                "listed_date": row["listed_date"],
                "status": row["status"],
            }
            if instrument is None:
                db.add(MarketInstrument(**payload))
            else:
                for key, value in payload.items():
                    setattr(instrument, key, value)
            inserted_instruments += 1

        db.flush()
        for row in conn.execute("select * from bars"):
            exists = db.scalar(
                select(MarketBar).where(
                    MarketBar.symbol == row["symbol"],
                    MarketBar.frequency == row["frequency"],
                    MarketBar.trade_time == row["trade_time"],
                )
            )
            if exists is not None:
                continue
            db.add(
                MarketBar(
                    symbol=row["symbol"],
                    frequency=row["frequency"],
                    trade_time=row["trade_time"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    amount=row["amount"],
                    adj_factor=row["adj_factor"],
                    source=row["source"],
                )
            )
            inserted_bars += 1
    db.commit()
    return {"market_instruments": inserted_instruments, "market_bars": inserted_bars}


def seed_strategy_versions(db: Session) -> int:
    changed = 0
    strategies = db.scalars(select(UserStrategy)).all()
    for strategy in strategies:
        exists = db.scalar(
            select(StrategyVersion).where(
                StrategyVersion.strategy_id == strategy.strategy_id,
                StrategyVersion.version == 1,
            )
        )
        if exists is not None:
            continue
        db.add(
            StrategyVersion(
                strategy_id=strategy.strategy_id,
                version=1,
                change_note="Seed version",
                strategy_json=strategy.strategy_json,
            )
        )
        changed += 1
    db.commit()
    return changed


def seed_backtest_demo(db: Session) -> dict[str, int]:
    report_path = BACKTEST_MODULE / "output" / "price_breakout_demo" / "report.json"
    if not report_path.exists():
        return {"backtest_runs": 0, "backtest_trades": 0, "backtest_equity_points": 0}

    report = read_json(report_path)
    backtest_id = "seed_price_breakout_demo_600519"
    run = db.get(BacktestRun, backtest_id)
    payload = {
        "backtest_id": backtest_id,
        "owner_id": None,
        "strategy_id": report["strategy_id"],
        "source_strategy_id": None,
        "strategy_version": None,
        "strategy_name": report["strategy_name"],
        "symbol": report["symbol"],
        "frequency": report["frequency"],
        "status": "completed",
        "start_date": report.get("start_date"),
        "end_date": report.get("end_date"),
        "metrics_json": report.get("metrics", {}),
        "report_json": report,
        "parameter_snapshot": None,
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
    return {
        "backtest_runs": 1,
        "backtest_trades": len(report.get("trades", [])),
        "backtest_equity_points": len(report.get("equity_curve", [])),
    }


def _legacy_connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _upgrade_sqlite_schema() -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "user_strategies" in tables:
        _add_missing_columns(
            inspector,
            "user_strategies",
            {
                "owner_id": "ALTER TABLE user_strategies ADD COLUMN owner_id INTEGER",
                "source_template_id": "ALTER TABLE user_strategies ADD COLUMN source_template_id VARCHAR(80)",
                "status": "ALTER TABLE user_strategies ADD COLUMN status VARCHAR(40) DEFAULT 'draft'",
            },
        )
    if "backtest_runs" in tables:
        _add_missing_columns(
            inspector,
            "backtest_runs",
            {
                "owner_id": "ALTER TABLE backtest_runs ADD COLUMN owner_id INTEGER",
                "source_strategy_id": "ALTER TABLE backtest_runs ADD COLUMN source_strategy_id VARCHAR(120)",
                "strategy_version": "ALTER TABLE backtest_runs ADD COLUMN strategy_version INTEGER",
                "parameter_snapshot": "ALTER TABLE backtest_runs ADD COLUMN parameter_snapshot JSON",
            },
        )


def _add_missing_columns(inspector, table_name: str, additions: dict[str, str]) -> None:
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for column_name, statement in additions.items():
            if column_name not in columns:
                conn.execute(text(statement))

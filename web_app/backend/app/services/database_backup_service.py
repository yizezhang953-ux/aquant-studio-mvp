"""Logical backup / restore as gzipped JSON (works for SQLite and PostgreSQL).

* Login sessions are never written to a backup (they are bearer credentials); restored users log in again.
* Password hashes are kept so accounts can be restored; treat backup files as confidential.
* Point BACKUP_DIR at persistent storage (a mounted volume), not the container's own disk.
"""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.services.database_service import TABLE_MODELS, get_database_status

FORMAT_VERSION = "2.0"
EXCLUDED_TABLES = {"user_sessions"}
# Parents before children, for inserts (reverse for deletes).
RESTORE_ORDER = [
    "users", "strategy_templates", "user_strategies", "strategy_versions", "market_instruments", "market_bars",
    "market_corporate_actions", "market_fx_rates", "backtest_runs", "backtest_trades", "backtest_equity_points",
    "audit_logs",
]


def create_database_backup(db: Session, output_dir: str | Path | None = None) -> dict[str, Any]:
    backup_dir = Path(output_dir or settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    filename = f"aquant-backup-{created_at.strftime('%Y%m%d-%H%M%S')}.json.gz"
    backup_path = backup_dir / filename

    tables = {name: _dump_table(db, model) for name, model in TABLE_MODELS.items() if name not in EXCLUDED_TABLES}
    payload = {
        "metadata": {
            "app": settings.app_name,
            "created_at": created_at.isoformat(),
            "dialect": engine.dialect.name,
            "format_version": FORMAT_VERSION,
            "excluded_tables": sorted(EXCLUDED_TABLES),
        },
        "status": get_database_status(db),
        "tables": tables,
    }
    with gzip.open(backup_path, "wt", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)

    row_counts = {table_name: len(rows) for table_name, rows in tables.items()}
    return {
        "backup_path": str(backup_path),
        "created_at": created_at.isoformat(),
        "dialect": engine.dialect.name,
        "table_count": len(tables),
        "row_counts": row_counts,
        "total_rows": sum(row_counts.values()),
    }


def read_backup_metadata(path: str | Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as file:
        payload = json.load(file)
    return {
        "metadata": payload.get("metadata", {}),
        "row_counts": {table_name: len(rows) for table_name, rows in payload.get("tables", {}).items()},
    }


def restore_database_backup(db: Session, path: str | Path) -> dict[str, Any]:
    """Replace the contents of every backed-up table with the backup (all sessions are dropped).

    Run migrations first (the schema must be at the current revision). Destructive: callers must
    confirm explicitly.
    """
    with gzip.open(path, "rt", encoding="utf-8") as file:
        payload = json.load(file)
    tables: dict[str, list[dict[str, Any]]] = payload.get("tables", {})
    unknown = set(tables) - set(TABLE_MODELS)
    if unknown:
        raise ValueError(f"backup contains unknown tables: {sorted(unknown)}")

    order = [name for name in RESTORE_ORDER if name in TABLE_MODELS]
    db.execute(delete(TABLE_MODELS["user_sessions"]))
    for name in reversed(order):  # clear every table (older backups may lack newer tables)
        db.execute(delete(TABLE_MODELS[name]))
    db.flush()
    restored: dict[str, int] = {}
    for name in order:
        rows = tables.get(name)
        if not rows:
            continue
        model = TABLE_MODELS[name]
        columns = {column.name: column for column in model.__table__.columns}
        prepared = []
        for row in rows:
            item = {}
            for key, value in row.items():
                column = columns.get(key)
                if column is None:
                    continue  # column removed since the backup was taken
                if isinstance(column.type, DateTime) and isinstance(value, str):
                    value = datetime.fromisoformat(value)
                item[key] = value
            prepared.append(item)
        db.execute(model.__table__.insert(), prepared)
        restored[name] = len(prepared)
    users = TABLE_MODELS["users"]
    if tables.get("users") and not db.scalar(select(func.count()).select_from(users).where(users.is_admin.is_(True))):
        first = db.scalar(select(func.min(users.id)))  # format 1.0 backups predate the admin role
        db.execute(users.__table__.update().where(users.id == first).values(is_admin=True))
    db.commit()
    _reset_postgres_sequences(db, order)
    return {"restored_rows": restored, "total_rows": sum(restored.values()), "source": str(path)}


def _reset_postgres_sequences(db: Session, tables: list[str]) -> None:
    if engine.dialect.name != "postgresql":
        return
    for name in tables:
        model = TABLE_MODELS[name]
        pk = list(model.__table__.primary_key.columns)
        if len(pk) != 1 or not str(pk[0].type).upper().startswith("INTEGER"):
            continue
        max_id = db.scalar(select(func.max(pk[0])))
        if max_id:
            db.execute(
                select(func.setval(func.pg_get_serial_sequence(name, pk[0].name), max_id))
            )
    db.commit()


def _dump_table(db: Session, model) -> list[dict[str, Any]]:
    return [_dump_model(row) for row in db.scalars(select(model)).all()]


def _dump_model(row) -> dict[str, Any]:
    return {column.name: _json_safe(getattr(row, column.name)) for column in row.__table__.columns}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value

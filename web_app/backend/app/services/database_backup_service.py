from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.services.database_service import TABLE_MODELS, get_database_status


def create_database_backup(db: Session, output_dir: str | Path | None = None) -> dict[str, Any]:
    backup_dir = Path(output_dir or settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    filename = f"aquant-backup-{created_at.strftime('%Y%m%d-%H%M%S')}.json.gz"
    backup_path = backup_dir / filename

    tables = {table_name: _dump_table(db, model) for table_name, model in TABLE_MODELS.items()}
    payload = {
        "metadata": {
            "app": settings.app_name,
            "created_at": created_at.isoformat(),
            "dialect": engine.dialect.name,
            "format_version": "1.0",
        },
        "status": get_database_status(db),
        "tables": tables,
    }
    with gzip.open(backup_path, "wt", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

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
        "row_counts": {
            table_name: len(rows) for table_name, rows in payload.get("tables", {}).items()
        },
    }


def _dump_table(db: Session, model) -> list[dict[str, Any]]:
    rows = db.scalars(select(model)).all()
    return [_dump_model(row) for row in rows]


def _dump_model(row) -> dict[str, Any]:
    output = {}
    for column in row.__table__.columns:
        output[column.name] = _json_safe(getattr(row, column.name))
    return output


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value

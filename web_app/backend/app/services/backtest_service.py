from __future__ import annotations

import sys
from typing import Any
from uuid import uuid4

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

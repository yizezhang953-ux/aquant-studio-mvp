from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RiskGatewayResult:
    accepted: bool
    reasons: list[str]
    metrics: dict[str, Any]


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def order_day(row: dict[str, str]) -> str:
    submitted_at = row.get("submitted_at", "")
    return submitted_at[:10]


def order_value(row: dict[str, str]) -> float:
    try:
        return float(row.get("quantity", 0)) * float(row.get("estimated_price", 0))
    except ValueError:
        return 0.0


def evaluate_runtime_risk(
    config: dict[str, Any],
    order: dict[str, Any],
    account_state: dict[str, Any],
    output_dir: Path,
) -> RiskGatewayResult:
    controls = config.get("runtime_risk_controls", {})
    if not controls.get("enabled", True):
        return RiskGatewayResult(True, [], {"enabled": False})

    reasons: list[str] = []
    metrics: dict[str, Any] = {"enabled": True}
    symbol = str(order.get("symbol", ""))
    source = str(order.get("source", ""))
    client_order_id = str(order.get("client_order_id", ""))
    side = order.get("side")
    quantity = int(order.get("quantity", 0) or 0)
    estimated_price = float(order.get("estimated_price", 0) or 0)
    proposed_value = quantity * estimated_price

    if controls.get("kill_switch_enabled"):
        reasons.append("runtime kill switch is enabled")

    allowed_sources = controls.get("allowed_sources", [])
    if allowed_sources and source not in allowed_sources:
        reasons.append(f"order source is not allowed: {source}")

    restricted_symbols = controls.get("restricted_symbols", [])
    if symbol in restricted_symbols:
        reasons.append(f"symbol is restricted by runtime risk controls: {symbol}")

    rows = read_csv_rows(output_dir / "orders.csv")
    today = today_utc()
    today_rows = [row for row in rows if order_day(row) == today]
    today_submitted = [row for row in today_rows if row.get("status") in {"submitted_to_broker", "filled"}]
    metrics["today_order_count"] = len(today_rows)
    metrics["today_submitted_count"] = len(today_submitted)
    metrics["today_submitted_value"] = round(sum(order_value(row) for row in today_submitted), 6)

    if controls.get("reject_duplicate_client_order_id", True):
        if any(row.get("client_order_id") == client_order_id for row in rows):
            reasons.append(f"duplicate client_order_id is rejected: {client_order_id}")

    max_daily_orders = controls.get("max_daily_orders")
    if isinstance(max_daily_orders, int) and len(today_rows) >= max_daily_orders:
        reasons.append("daily order count limit reached")

    max_daily_submitted_orders = controls.get("max_daily_submitted_orders")
    if isinstance(max_daily_submitted_orders, int) and len(today_submitted) >= max_daily_submitted_orders:
        reasons.append("daily submitted order limit reached")

    max_daily_submitted_value = controls.get("max_daily_submitted_value")
    if isinstance(max_daily_submitted_value, (int, float)):
        if metrics["today_submitted_value"] + proposed_value > float(max_daily_submitted_value):
            reasons.append("daily submitted value limit would be exceeded")

    max_position_pct = controls.get("max_symbol_position_value_pct")
    if side == "buy" and isinstance(max_position_pct, (int, float)):
        cash = float(account_state.get("cash", 0) or 0)
        positions = account_state.get("positions", {})
        current_qty = int(positions.get(symbol, 0))
        estimated_symbol_value = (current_qty * estimated_price) + proposed_value
        account_equity_proxy = cash + estimated_symbol_value
        metrics["estimated_symbol_value_after_order"] = round(estimated_symbol_value, 6)
        metrics["account_equity_proxy"] = round(account_equity_proxy, 6)
        if account_equity_proxy > 0 and estimated_symbol_value / account_equity_proxy > float(max_position_pct):
            reasons.append("symbol position value limit would be exceeded")

    daily_loss_limit = controls.get("max_daily_loss")
    if isinstance(daily_loss_limit, (int, float)):
        daily_realized_pnl = float(account_state.get("daily_realized_pnl", 0) or 0)
        metrics["daily_realized_pnl"] = daily_realized_pnl
        if daily_realized_pnl <= -abs(float(daily_loss_limit)):
            reasons.append("daily loss limit reached")

    return RiskGatewayResult(not reasons, reasons, metrics)

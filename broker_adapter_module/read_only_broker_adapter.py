from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .broker_adapter import BrokerAdapter, BrokerOrderAck, BrokerFill
except ImportError:
    from broker_adapter import BrokerAdapter, BrokerOrderAck, BrokerFill


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class ReadOnlyBrokerAdapter(BrokerAdapter):
    def __init__(self, snapshot_path: Path):
        self.snapshot_path = snapshot_path
        self.snapshot = read_json(snapshot_path)

    def query_account(self) -> dict[str, Any]:
        return dict(self.snapshot.get("account", {}))

    def query_positions(self) -> dict[str, int]:
        positions = self.snapshot.get("positions", {})
        return {symbol: int(row.get("quantity", 0)) for symbol, row in positions.items()}

    def query_position_details(self) -> dict[str, Any]:
        return dict(self.snapshot.get("positions", {}))

    def submit_order(self, order: Any) -> tuple[BrokerOrderAck, BrokerFill | None]:
        ack = BrokerOrderAck(
            broker_order_id="READONLY-BLOCKED",
            gateway_order_id=getattr(order, "gateway_order_id", "unknown"),
            status="rejected",
            message="read-only broker adapter blocks order submission",
            acknowledged_at=now_iso(),
        )
        return ack, None

    def cancel_order(self, broker_order_id: str) -> dict[str, Any]:
        return {"broker_order_id": broker_order_id, "status": "read_only_noop"}

    def query_order(self, broker_order_id: str) -> dict[str, Any]:
        for order in self.snapshot.get("orders", []):
            if order.get("broker_order_id") == broker_order_id:
                return dict(order)
        return {"broker_order_id": broker_order_id, "status": "not_found"}

    def query_fills(self, broker_order_id: str | None = None) -> list[BrokerFill]:
        fills = []
        for row in self.snapshot.get("fills", []):
            if broker_order_id is not None and row.get("broker_order_id") != broker_order_id:
                continue
            fills.append(
                BrokerFill(
                    fill_id=row["fill_id"],
                    broker_order_id=row["broker_order_id"],
                    gateway_order_id=row.get("gateway_order_id", ""),
                    symbol=row["symbol"],
                    side=row["side"],
                    quantity=int(row["quantity"]),
                    fill_price=float(row["fill_price"]),
                    amount=float(row["amount"]),
                    fee=float(row.get("fee", 0)),
                    fee_details=dict(row.get("fee_details", {})),
                    filled_at=row["filled_at"],
                )
            )
        return fills

    def export_normalized_snapshot(self) -> dict[str, Any]:
        return {
            "account": self.query_account(),
            "positions": self.query_position_details(),
            "position_quantities": self.query_positions(),
            "orders": list(self.snapshot.get("orders", [])),
            "fills": [asdict(fill) for fill in self.query_fills()],
            "synced_at": now_iso(),
            "mode": "read_only",
        }

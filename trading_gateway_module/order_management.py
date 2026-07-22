from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ORDER_STATUSES = {
    "received",
    "risk_accepted",
    "risk_rejected",
    "submitted_to_broker",
    "filled",
    "failed",
}

ALLOWED_TRANSITIONS = {
    "received": {"risk_accepted", "risk_rejected", "failed"},
    "risk_accepted": {"submitted_to_broker", "failed"},
    "submitted_to_broker": {"filled", "failed"},
    "risk_rejected": set(),
    "filled": set(),
    "failed": set(),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class OrderLifecycleEvent:
    timestamp: str
    gateway_order_id: str
    previous_status: str
    new_status: str
    event_type: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagedOrder:
    gateway_order_id: str
    client_order_id: str
    strategy_id: str
    symbol: str
    side: str
    order_type: str
    quantity: int
    estimated_price: float
    status: str
    source: str
    reason: str
    created_at: str
    updated_at: str
    risk_reasons: list[str] = field(default_factory=list)
    broker_order_id: str | None = None
    fill_id: str | None = None


class OrderStateError(ValueError):
    pass


class OrderManagementSystem:
    def __init__(self) -> None:
        self.orders: dict[str, ManagedOrder] = {}
        self.events: list[OrderLifecycleEvent] = []

    def receive_order(self, gateway_order_id: str, ticket: dict[str, Any], timestamp: str | None = None) -> ManagedOrder:
        created_at = timestamp or now_iso()
        order = ManagedOrder(
            gateway_order_id=gateway_order_id,
            client_order_id=str(ticket["client_order_id"]),
            strategy_id=str(ticket["strategy_id"]),
            symbol=str(ticket["symbol"]),
            side=str(ticket["side"]),
            order_type=str(ticket["order_type"]),
            quantity=int(ticket["quantity"]),
            estimated_price=float(ticket["estimated_price"]),
            status="received",
            source=str(ticket.get("source", "")),
            reason=str(ticket.get("reason", "")),
            created_at=created_at,
            updated_at=created_at,
        )
        self.orders[gateway_order_id] = order
        self.events.append(
            OrderLifecycleEvent(
                timestamp=created_at,
                gateway_order_id=gateway_order_id,
                previous_status="",
                new_status="received",
                event_type="order_received",
                message="order ticket entered OMS",
                payload={"client_order_id": order.client_order_id, "source": order.source},
            )
        )
        return order

    def apply_risk_decision(self, gateway_order_id: str, accepted: bool, reasons: list[str]) -> ManagedOrder:
        new_status = "risk_accepted" if accepted else "risk_rejected"
        message = "risk check passed" if accepted else "; ".join(reasons)
        return self.transition(
            gateway_order_id,
            new_status,
            "risk_check",
            message,
            {"risk_reasons": reasons},
        )

    def mark_submitted_to_broker(self, gateway_order_id: str, broker_order_id: str | None = None) -> ManagedOrder:
        return self.transition(
            gateway_order_id,
            "submitted_to_broker",
            "broker_submit",
            "order submitted to configured broker adapter",
            {"broker_order_id": broker_order_id},
        )

    def mark_filled(self, gateway_order_id: str, fill: dict[str, Any]) -> ManagedOrder:
        return self.transition(
            gateway_order_id,
            "filled",
            "order_filled",
            "broker adapter reported fill",
            {"fill": fill},
        )

    def mark_failed(self, gateway_order_id: str, message: str, payload: dict[str, Any] | None = None) -> ManagedOrder:
        return self.transition(gateway_order_id, "failed", "order_failed", message, payload or {})

    def transition(
        self,
        gateway_order_id: str,
        new_status: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> ManagedOrder:
        if new_status not in ORDER_STATUSES:
            raise OrderStateError(f"unknown order status: {new_status}")
        if gateway_order_id not in self.orders:
            raise OrderStateError(f"unknown gateway order: {gateway_order_id}")

        order = self.orders[gateway_order_id]
        previous = order.status
        if new_status not in ALLOWED_TRANSITIONS[previous]:
            raise OrderStateError(f"invalid order transition: {previous} -> {new_status}")

        timestamp = now_iso()
        order.status = new_status
        order.updated_at = timestamp
        if payload:
            if "risk_reasons" in payload:
                order.risk_reasons = list(payload["risk_reasons"])
            if "broker_order_id" in payload:
                order.broker_order_id = payload["broker_order_id"]
            fill = payload.get("fill")
            if isinstance(fill, dict):
                order.fill_id = fill.get("fill_id")

        self.events.append(
            OrderLifecycleEvent(
                timestamp=timestamp,
                gateway_order_id=gateway_order_id,
                previous_status=previous,
                new_status=new_status,
                event_type=event_type,
                message=message,
                payload=payload or {},
            )
        )
        return order

    def snapshot(self) -> dict[str, Any]:
        return {
            "orders": [asdict(order) for order in self.orders.values()],
            "events": [asdict(event) for event in self.events],
        }

    def write_outputs(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "oms_orders.json").write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        events_path = output_dir / "order_lifecycle.csv"
        with events_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "timestamp",
                    "gateway_order_id",
                    "previous_status",
                    "new_status",
                    "event_type",
                    "message",
                    "payload",
                ],
            )
            writer.writeheader()
            for event in self.events:
                row = asdict(event)
                row["payload"] = json.dumps(row["payload"], ensure_ascii=False, sort_keys=True)
                writer.writerow(row)

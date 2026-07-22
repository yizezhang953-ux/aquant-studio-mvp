from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_rules_module.market_rules import calculate_fee_breakdown, read_json as read_market_rules_json, validate_market_order


@dataclass
class SimEvent:
    event_time: str
    event_type: str
    status: str
    message: str
    payload: dict[str, Any]


@dataclass
class SimOrder:
    sim_order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: int
    estimated_price: float
    status: str
    submitted_at: str
    filled_quantity: int = 0
    remaining_quantity: int = 0


@dataclass
class SimFill:
    fill_id: str
    sim_order_id: str
    symbol: str
    side: str
    quantity: int
    fill_price: float
    amount: float
    fee: float
    filled_at: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class EventDrivenPaperTrader:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.cash = float(config["account"]["initial_cash"])
        self.positions = dict(config["account"].get("initial_positions", {}))
        self.events: list[SimEvent] = []
        self.orders: list[SimOrder] = []
        self.fills: list[SimFill] = []
        rules_path = ROOT / config.get("market_rules_path", "market_rules_module/configs/market_rules.json")
        self.market_rules = read_market_rules_json(rules_path)

    def emit(self, event_type: str, status: str, message: str, payload: dict[str, Any]) -> None:
        self.events.append(SimEvent(now_iso(), event_type, status, message, payload))

    def snapshot(self) -> dict[str, Any]:
        return {
            "cash": round(self.cash, 6),
            "positions": dict(self.positions),
            "position_quantity_total": int(sum(self.positions.values())),
            "updated_at": now_iso(),
        }

    def submit(self, ticket: dict[str, Any], sequence: int) -> SimOrder:
        order = SimOrder(
            sim_order_id=f"SIM-{sequence:04d}",
            client_order_id=str(ticket["client_order_id"]),
            symbol=str(ticket["symbol"]),
            side=str(ticket["side"]),
            order_type=str(ticket["order_type"]),
            quantity=int(ticket["quantity"]),
            estimated_price=float(ticket["estimated_price"]),
            status="submitted",
            submitted_at=now_iso(),
            remaining_quantity=int(ticket["quantity"]),
        )
        self.orders.append(order)
        self.emit("order_submitted", "submitted", "paper order submitted", asdict(order))
        return order

    def reject(self, order: SimOrder, reasons: list[str]) -> None:
        order.status = "rejected"
        self.emit("order_rejected", "rejected", "; ".join(reasons), asdict(order))

    def fill(self, order: SimOrder, quantity: int) -> None:
        if quantity <= 0:
            return
        slippage_rate = float(self.config["execution"].get("slippage_rate", 0))
        fill_price = order.estimated_price * (1 + slippage_rate if order.side == "buy" else 1 - slippage_rate)
        amount = quantity * fill_price
        fee_breakdown = calculate_fee_breakdown(self.market_rules, order.symbol, order.side, amount)
        fee = fee_breakdown.total_fee
        current_qty = int(self.positions.get(order.symbol, 0))

        if order.side == "buy":
            self.cash -= amount + fee
            self.positions[order.symbol] = current_qty + quantity
        else:
            self.cash += amount - fee
            self.positions[order.symbol] = current_qty - quantity

        order.filled_quantity += quantity
        order.remaining_quantity -= quantity
        order.status = "filled" if order.remaining_quantity == 0 else "partially_filled"
        fill = SimFill(
            fill_id=f"FILL-{order.sim_order_id}-{len(self.fills) + 1:03d}",
            sim_order_id=order.sim_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            fill_price=round(fill_price, 6),
            amount=round(amount, 6),
            fee=round(fee, 6),
            filled_at=now_iso(),
        )
        self.fills.append(fill)
        self.emit("order_filled", order.status, "paper simulator created fill", {**asdict(fill), "fee_details": fee_breakdown.components})

    def cancel_remaining(self, order: SimOrder) -> None:
        if order.remaining_quantity <= 0:
            return
        order.status = "canceled"
        self.emit("order_canceled", "canceled", "remaining quantity canceled by simulation policy", asdict(order))

    def run(self) -> dict[str, Any]:
        snapshots = [self.snapshot()]
        for index, ticket in enumerate(self.config.get("orders", []), start=1):
            order = self.submit(ticket, index)
            check = validate_market_order(self.market_rules, ticket, {"cash": self.cash, "positions": self.positions})
            if not check.accepted:
                self.reject(order, check.reasons)
                snapshots.append(self.snapshot())
                continue

            fill_policy = ticket.get("fill_policy", {})
            max_fill_quantity = int(fill_policy.get("max_fill_quantity", order.quantity))
            fill_quantity = min(order.quantity, max_fill_quantity)
            gross_amount = fill_quantity * order.estimated_price
            if order.side == "buy" and gross_amount > self.cash:
                self.reject(order, ["cash is insufficient in event-driven paper account"])
                snapshots.append(self.snapshot())
                continue
            self.fill(order, fill_quantity)
            if fill_policy.get("cancel_remaining") and order.remaining_quantity > 0:
                self.cancel_remaining(order)
            snapshots.append(self.snapshot())

        return {
            "ok": True,
            "orders": [asdict(order) for order in self.orders],
            "fills": [asdict(fill) for fill in self.fills],
            "events": [asdict(event) for event in self.events],
            "account_snapshots": snapshots,
            "final_account": snapshots[-1],
        }


def write_outputs(report: dict[str, Any], output_dir: Path) -> None:
    write_json(output_dir / "simulation_report.json", report)
    write_csv(output_dir / "orders.csv", report["orders"])
    write_csv(output_dir / "fills.csv", report["fills"])
    events = []
    for event in report["events"]:
        row = dict(event)
        row["payload"] = json.dumps(row["payload"], ensure_ascii=False, sort_keys=True)
        events.append(row)
    write_csv(output_dir / "events.csv", events)
    write_csv(output_dir / "account_snapshots.csv", report["account_snapshots"])


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant event-driven paper trader")
    parser.add_argument("--config", default="simulation_module/configs/event_driven_demo.json")
    parser.add_argument("--output-dir", default="simulation_module/output/event_driven_demo")
    args = parser.parse_args()
    trader = EventDrivenPaperTrader(read_json(Path(args.config)))
    report = trader.run()
    write_outputs(report, Path(args.output_dir))
    print(json.dumps({"ok": True, "orders": len(report["orders"]), "fills": len(report["fills"]), "output_dir": args.output_dir}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

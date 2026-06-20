from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SH|SZ)$")


@dataclass
class GatewayDecision:
    accepted: bool
    status: str
    reasons: list[str]


@dataclass
class GatewayOrder:
    gateway_order_id: str
    client_order_id: str
    strategy_id: str
    symbol: str
    side: str
    order_type: str
    quantity: int
    estimated_price: float
    submitted_at: str
    status: str
    reason: str
    source: str


@dataclass
class GatewayFill:
    fill_id: str
    gateway_order_id: str
    symbol: str
    side: str
    quantity: int
    fill_price: float
    amount: float
    fee: float
    filled_at: str


@dataclass
class AuditEvent:
    timestamp: str
    event_type: str
    status: str
    message: str
    payload: dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_csv(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def flatten_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def validate_order(config: dict[str, Any], order: dict[str, Any], account_state: dict[str, Any]) -> GatewayDecision:
    reasons: list[str] = []
    risk = config["risk_limits"]

    if config.get("mode") != "sandbox":
        reasons.append("only sandbox mode is enabled in this MVP")
    if config.get("live_trading_enabled"):
        reasons.append("live_trading_enabled must remain false for this stage")

    symbol = order.get("symbol")
    side = order.get("side")
    quantity = order.get("quantity")
    estimated_price = order.get("estimated_price")

    if not isinstance(symbol, str) or not SYMBOL_PATTERN.match(symbol):
        reasons.append(f"invalid A-share symbol: {symbol}")
    elif symbol not in risk["allowed_symbols"]:
        reasons.append(f"symbol is not allowed by gateway risk limits: {symbol}")

    if side not in risk["allowed_sides"]:
        reasons.append(f"unsupported side: {side}")
    if not isinstance(quantity, int) or quantity <= 0:
        reasons.append("quantity must be a positive integer")
    elif quantity > int(risk["max_quantity"]):
        reasons.append("quantity exceeds max_quantity")

    if not isinstance(estimated_price, (int, float)) or estimated_price <= 0:
        reasons.append("estimated_price must be positive")
    else:
        order_value = float(quantity or 0) * float(estimated_price)
        if order_value > float(risk["max_order_value"]):
            reasons.append("order value exceeds max_order_value")
        if side == "buy" and order_value > float(account_state["cash"]):
            reasons.append("cash is insufficient")

    if risk.get("require_a_share_lot_size") and isinstance(quantity, int) and quantity % 100 != 0:
        reasons.append("quantity must be a multiple of 100 when lot-size control is enabled")

    positions = account_state.get("positions", {})
    held_qty = int(positions.get(symbol, 0)) if symbol else 0
    if side == "sell" and risk.get("reject_short_sell", True) and isinstance(quantity, int) and quantity > held_qty:
        reasons.append("short sell is rejected by gateway")

    return GatewayDecision(accepted=not reasons, status="accepted" if not reasons else "rejected", reasons=reasons)


class SandboxBrokerAdapter:
    def __init__(self, config: dict[str, Any], account_state: dict[str, Any]):
        self.config = config
        self.account_state = account_state

    def submit_order(self, order: GatewayOrder) -> GatewayFill:
        account = self.config["account"]
        fee_rate = float(account["fee_rate"])
        slippage_rate = float(account["slippage_rate"])
        if order.side == "buy":
            fill_price = order.estimated_price * (1 + slippage_rate)
        else:
            fill_price = order.estimated_price * (1 - slippage_rate)
        amount = order.quantity * fill_price
        fee = amount * fee_rate
        positions = self.account_state.setdefault("positions", {})
        current_qty = int(positions.get(order.symbol, 0))

        if order.side == "buy":
            self.account_state["cash"] -= amount + fee
            positions[order.symbol] = current_qty + order.quantity
        else:
            self.account_state["cash"] += amount - fee
            positions[order.symbol] = current_qty - order.quantity

        self.account_state["cash"] = round(self.account_state["cash"], 6)
        return GatewayFill(
            fill_id=f"FILL-{order.gateway_order_id}",
            gateway_order_id=order.gateway_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=round(fill_price, 6),
            amount=round(amount, 6),
            fee=round(fee, 6),
            filled_at=now_iso(),
        )


def load_or_create_account_state(config: dict[str, Any], path: Path) -> dict[str, Any]:
    if path.exists():
        return read_json(path)
    return {
        "account_id": config["account"]["account_id"],
        "cash": float(config["account"]["initial_cash"]),
        "positions": dict(config["account"].get("initial_positions", {})),
        "updated_at": now_iso(),
    }


def process_order(config_path: Path, order_path: Path, output_dir: Path) -> dict[str, Any]:
    config = read_json(config_path)
    order_ticket = read_json(order_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    account_state_path = output_dir / "account_state.json"
    account_state = load_or_create_account_state(config, account_state_path)
    timestamp = now_iso()

    decision = validate_order(config, order_ticket, account_state)
    gateway_order = GatewayOrder(
        gateway_order_id=f"GW-{timestamp.replace(':', '').replace('-', '')}",
        client_order_id=order_ticket["client_order_id"],
        strategy_id=order_ticket["strategy_id"],
        symbol=order_ticket["symbol"],
        side=order_ticket["side"],
        order_type=order_ticket["order_type"],
        quantity=int(order_ticket["quantity"]),
        estimated_price=float(order_ticket["estimated_price"]),
        submitted_at=timestamp,
        status=decision.status,
        reason=order_ticket.get("reason", ""),
        source=order_ticket.get("source", ""),
    )

    audit_events: list[AuditEvent] = [
        AuditEvent(timestamp, "order_received", "received", "gateway received order ticket", order_ticket),
        AuditEvent(timestamp, "risk_check", decision.status, "; ".join(decision.reasons) or "risk check passed", asdict(gateway_order)),
    ]
    result: dict[str, Any] = {
        "gateway_id": config["gateway_id"],
        "mode": config["mode"],
        "decision": asdict(decision),
        "order": asdict(gateway_order),
        "fill": None,
        "account_state": account_state,
    }

    if decision.accepted:
        adapter = SandboxBrokerAdapter(config, account_state)
        fill = adapter.submit_order(gateway_order)
        account_state["updated_at"] = now_iso()
        gateway_order.status = "filled"
        result["order"] = asdict(gateway_order)
        result["fill"] = asdict(fill)
        result["account_state"] = account_state
        audit_events.append(AuditEvent(fill.filled_at, "order_filled", "filled", "sandbox broker filled order", asdict(fill)))
        append_csv(output_dir / "fills.csv", asdict(fill))

    write_json(account_state_path, account_state)
    write_json(output_dir / "last_order_result.json", result)
    append_csv(output_dir / "orders.csv", asdict(gateway_order))
    for event in audit_events:
        row = asdict(event)
        row["payload"] = flatten_payload(row["payload"])
        append_csv(output_dir / "audit_log.csv", row)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant trading gateway sandbox")
    parser.add_argument("order")
    parser.add_argument("--config", default="trading_gateway_module/configs/sandbox_gateway.json")
    parser.add_argument("--output-dir", default="trading_gateway_module/output/sandbox")
    args = parser.parse_args()

    result = process_order(Path(args.config), Path(args.order), Path(args.output_dir))
    print(json.dumps({"ok": True, "decision": result["decision"], "order": result["order"], "fill": result["fill"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

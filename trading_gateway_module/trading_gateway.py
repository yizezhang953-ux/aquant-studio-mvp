from __future__ import annotations

import argparse
import csv
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_rules_module.market_rules import read_json as read_market_rules_json, validate_market_order
from broker_adapter_module.broker_adapter import SandboxBrokerAdapter as BrokerSandboxAdapter

try:
    from .order_management import OrderManagementSystem
    from .risk_gateway import evaluate_runtime_risk
except ImportError:
    from order_management import OrderManagementSystem
    from risk_gateway import evaluate_runtime_risk


SYMBOL_PATTERN = re.compile(r"^([0-9]{6}\.(SH|SZ)|[0-9]{5}\.HK)$")


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
    broker_order_id: str
    gateway_order_id: str
    symbol: str
    side: str
    quantity: int
    fill_price: float
    amount: float
    fee: float
    fee_details: dict[str, float]
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


def new_gateway_order_id(timestamp: str) -> str:
    compact_time = timestamp.replace(":", "").replace("-", "")
    return f"GW-{compact_time}-{uuid.uuid4().hex[:8].upper()}"


def load_market_rules(config: dict[str, Any]) -> dict[str, Any]:
    path = Path(config.get("market_rules_path", "market_rules_module/configs/market_rules.json"))
    if not path.is_absolute():
        path = ROOT / path
    return read_market_rules_json(path)


def validate_order(
    config: dict[str, Any],
    order: dict[str, Any],
    account_state: dict[str, Any],
    output_dir: Path | None = None,
) -> GatewayDecision:
    reasons: list[str] = []
    risk = config["risk_limits"]
    market_rules = load_market_rules(config)

    if config.get("mode") != "sandbox":
        reasons.append("only sandbox mode is enabled in this MVP")
    if config.get("live_trading_enabled"):
        reasons.append("live_trading_enabled must remain false for this stage")

    symbol = order.get("symbol")
    side = order.get("side")
    quantity = order.get("quantity")
    estimated_price = order.get("estimated_price")

    if not isinstance(symbol, str) or not SYMBOL_PATTERN.match(symbol):
        reasons.append(f"invalid supported market symbol: {symbol}")
    elif symbol not in risk["allowed_symbols"]:
        reasons.append(f"symbol is not allowed by gateway risk limits: {symbol}")
    else:
        market_check = validate_market_order(market_rules, order, account_state)
        reasons.extend(market_check.reasons)

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

    positions = account_state.get("positions", {})
    held_qty = int(positions.get(symbol, 0)) if symbol else 0
    if side == "sell" and risk.get("reject_short_sell", True) and isinstance(quantity, int) and quantity > held_qty:
        reasons.append("short sell is rejected by gateway")

    if output_dir is not None:
        runtime_result = evaluate_runtime_risk(config, order, account_state, output_dir)
        reasons.extend(runtime_result.reasons)

    return GatewayDecision(accepted=not reasons, status="accepted" if not reasons else "rejected", reasons=reasons)


def validate_live_trading_policy(config: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    policy = config.get("live_trading_policy", {})
    mode = policy.get("mode", "paper_trading")
    allowed_modes = policy.get(
        "allowed_modes",
        ["research_only", "paper_trading", "broker_shadow", "manual_confirm_live", "limited_auto_live"],
    )

    if mode not in allowed_modes:
        reasons.append(f"unsupported live trading policy mode: {mode}")
    if config.get("live_trading_enabled"):
        reasons.append("live_trading_enabled must remain false until final live approval")
    if policy.get("allow_real_broker_submit"):
        reasons.append("real broker submission is blocked in stage 1")
    if mode in {"manual_confirm_live", "limited_auto_live"} and not policy.get("manual_approval_required", True):
        reasons.append("manual approval is required before any live-capable mode")
    return reasons


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
    gateway_order_id = new_gateway_order_id(timestamp)
    oms = OrderManagementSystem()
    managed_order = oms.receive_order(gateway_order_id, order_ticket, timestamp)

    decision = validate_order(config, order_ticket, account_state, output_dir)
    policy_reasons = validate_live_trading_policy(config)
    if policy_reasons:
        decision.reasons.extend(policy_reasons)
        decision.accepted = False
        decision.status = "rejected"
    managed_order = oms.apply_risk_decision(gateway_order_id, decision.accepted, decision.reasons)
    gateway_order = GatewayOrder(
        gateway_order_id=gateway_order_id,
        client_order_id=order_ticket["client_order_id"],
        strategy_id=order_ticket["strategy_id"],
        symbol=order_ticket["symbol"],
        side=order_ticket["side"],
        order_type=order_ticket["order_type"],
        quantity=int(order_ticket["quantity"]),
        estimated_price=float(order_ticket["estimated_price"]),
        submitted_at=timestamp,
        status=managed_order.status,
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
        "broker_ack": None,
        "account_state": account_state,
        "oms": oms.snapshot(),
    }

    if decision.accepted:
        managed_order = oms.mark_submitted_to_broker(gateway_order.gateway_order_id)
        gateway_order.status = managed_order.status
        adapter = BrokerSandboxAdapter(config, account_state)
        broker_ack, broker_fill = adapter.submit_order(gateway_order)
        account_state["updated_at"] = now_iso()
        result["broker_ack"] = asdict(broker_ack)
        managed_order.broker_order_id = broker_ack.broker_order_id
        audit_events.append(AuditEvent(broker_ack.acknowledged_at, "broker_ack", broker_ack.status, broker_ack.message, asdict(broker_ack)))
        if broker_fill is not None:
            fill = GatewayFill(
                fill_id=broker_fill.fill_id,
                broker_order_id=broker_fill.broker_order_id,
                gateway_order_id=broker_fill.gateway_order_id,
                symbol=broker_fill.symbol,
                side=broker_fill.side,
                quantity=broker_fill.quantity,
                fill_price=broker_fill.fill_price,
                amount=broker_fill.amount,
                fee=broker_fill.fee,
                fee_details=broker_fill.fee_details,
                filled_at=broker_fill.filled_at,
            )
            managed_order = oms.mark_filled(gateway_order.gateway_order_id, asdict(fill))
            gateway_order.status = managed_order.status
            result["fill"] = asdict(fill)
            audit_events.append(AuditEvent(fill.filled_at, "order_filled", "filled", "sandbox broker filled order", asdict(fill)))
            append_csv(output_dir / "fills.csv", asdict(fill))
        result["order"] = asdict(gateway_order)
        result["account_state"] = account_state

    result["oms"] = oms.snapshot()
    write_json(account_state_path, account_state)
    write_json(output_dir / "last_order_result.json", result)
    oms.write_outputs(output_dir)
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

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from broker_adapter_module.read_only_broker_adapter import ReadOnlyBrokerAdapter
from market_rules_module.market_rules import calculate_fee_breakdown, read_json as read_market_rules_json, validate_market_order


@dataclass
class ShadowOrderResult:
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    estimated_price: float
    feasible: bool
    reasons: list[str]
    estimated_amount: float
    estimated_fee: float
    fee_details: dict[str, float]
    would_submit: bool


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def available_cash(account: dict[str, Any], symbol: str) -> float:
    cash = account.get("cash", {})
    if isinstance(cash, (int, float)):
        return float(cash)
    if symbol.endswith(".HK"):
        return float(cash.get("HKD", 0))
    return float(cash.get("CNY", 0))


def account_state_from_snapshot(adapter: ReadOnlyBrokerAdapter) -> dict[str, Any]:
    details = adapter.query_position_details()
    return {
        "cash": 0,
        "positions": {symbol: int(row.get("quantity", 0)) for symbol, row in details.items()},
        "available_positions": {symbol: int(row.get("sellable_quantity", row.get("quantity", 0))) for symbol, row in details.items()},
    }


def evaluate_shadow_orders(config: dict[str, Any]) -> dict[str, Any]:
    adapter = ReadOnlyBrokerAdapter(ROOT / config["snapshot_path"])
    account = adapter.query_account()
    account_state = account_state_from_snapshot(adapter)
    market_rules = read_market_rules_json(ROOT / config.get("market_rules_path", "market_rules_module/configs/market_rules.json"))
    results: list[ShadowOrderResult] = []

    for order in config.get("theoretical_orders", []):
        reasons: list[str] = []
        check = validate_market_order(market_rules, order, account_state)
        reasons.extend(check.reasons)
        quantity = int(order["quantity"])
        estimated_price = float(order["estimated_price"])
        gross_amount = quantity * estimated_price
        fee = calculate_fee_breakdown(market_rules, order["symbol"], order["side"], gross_amount)
        if order["side"] == "buy" and gross_amount + fee.total_fee > available_cash(account, order["symbol"]):
            reasons.append("read-only account cash is insufficient for this theoretical order")
        if order["side"] == "sell":
            sellable = account_state["available_positions"].get(order["symbol"], 0)
            if quantity > sellable:
                reasons.append("read-only account sellable quantity is insufficient")
        results.append(
            ShadowOrderResult(
                client_order_id=order["client_order_id"],
                symbol=order["symbol"],
                side=order["side"],
                quantity=quantity,
                estimated_price=estimated_price,
                feasible=not reasons,
                reasons=reasons,
                estimated_amount=round(gross_amount, 6),
                estimated_fee=fee.total_fee,
                fee_details=fee.components,
                would_submit=False,
            )
        )

    return {
        "ok": True,
        "mode": "shadow_trading",
        "would_submit_any_order": False,
        "snapshot_path": config["snapshot_path"],
        "generated_at": now_iso(),
        "account": account,
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant shadow trading evaluator")
    parser.add_argument("--config", default="shadow_trading_module/configs/shadow_demo.json")
    parser.add_argument("--output", default="shadow_trading_module/output/shadow_report.json")
    args = parser.parse_args()
    report = evaluate_shadow_orders(read_json(Path(args.config)))
    write_json(Path(args.output), report)
    print(json.dumps({"ok": True, "orders": len(report["results"]), "would_submit_any_order": False, "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

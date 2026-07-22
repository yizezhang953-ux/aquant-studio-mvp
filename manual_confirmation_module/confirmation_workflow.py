from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PendingOrder:
    approval_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: int
    estimated_price: float
    status: str
    reasons: list[str]
    created_at: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_pending_orders(shadow_report: dict[str, Any]) -> dict[str, Any]:
    pending: list[PendingOrder] = []
    for index, result in enumerate(shadow_report.get("results", []), start=1):
        if not result.get("feasible"):
            continue
        pending.append(
            PendingOrder(
                approval_id=f"APPROVAL-{index:04d}",
                client_order_id=result["client_order_id"],
                symbol=result["symbol"],
                side=result["side"],
                order_type="limit",
                quantity=int(result["quantity"]),
                estimated_price=float(result["estimated_price"]),
                status="pending_manual_confirmation",
                reasons=list(result.get("reasons", [])),
                created_at=now_iso(),
            )
        )
    return {
        "ok": True,
        "mode": "manual_confirmation_prepare",
        "source_shadow_report": shadow_report.get("generated_at"),
        "pending_orders": [asdict(order) for order in pending],
    }


def apply_approvals(pending_package: dict[str, Any], approvals: dict[str, Any]) -> dict[str, Any]:
    approval_map = {item["approval_id"]: item for item in approvals.get("approvals", [])}
    approved_orders = []
    rejected_orders = []
    for order in pending_package.get("pending_orders", []):
        approval = approval_map.get(order["approval_id"])
        if not approval:
            rejected_orders.append({**order, "status": "missing_manual_approval"})
            continue
        if approval.get("decision") != "approved":
            rejected_orders.append(
                {
                    **order,
                    "status": "manual_rejected",
                    "reviewed_by": approval.get("reviewed_by"),
                    "review_note": approval.get("review_note", ""),
                }
            )
            continue
        approved_orders.append(
            {
                "client_order_id": f"{order['client_order_id']}-APPROVED",
                "strategy_id": "manual_confirmed_shadow_order",
                "symbol": order["symbol"],
                "side": order["side"],
                "order_type": order["order_type"],
                "quantity": order["quantity"],
                "estimated_price": order["estimated_price"],
                "reason": "manual_confirmed_shadow_trade",
                "source": "manual_confirm_test",
                "manual_approval": {
                    "approval_id": order["approval_id"],
                    "reviewed_by": approval["reviewed_by"],
                    "reviewed_at": approval.get("reviewed_at", now_iso()),
                    "review_note": approval.get("review_note", "")
                }
            }
        )
    return {
        "ok": True,
        "mode": "manual_confirmation_apply",
        "approved_orders": approved_orders,
        "rejected_orders": rejected_orders,
        "applied_at": now_iso(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant manual order confirmation workflow")
    parser.add_argument("mode", choices=["prepare", "apply"])
    parser.add_argument("--shadow-report", default="shadow_trading_module/output/stage7_shadow_report.json")
    parser.add_argument("--pending", default="manual_confirmation_module/output/pending_orders.json")
    parser.add_argument("--approvals", default="manual_confirmation_module/configs/manual_approvals.json")
    parser.add_argument("--output", default="manual_confirmation_module/output/manual_confirmation_result.json")
    args = parser.parse_args()

    if args.mode == "prepare":
        package = prepare_pending_orders(read_json(Path(args.shadow_report)))
        write_json(Path(args.pending), package)
        print(json.dumps({"ok": True, "pending": len(package["pending_orders"]), "output": args.pending}, ensure_ascii=False, indent=2))
        return

    result = apply_approvals(read_json(Path(args.pending)), read_json(Path(args.approvals)))
    write_json(Path(args.output), result)
    print(json.dumps({"ok": True, "approved": len(result["approved_orders"]), "rejected": len(result["rejected_orders"]), "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

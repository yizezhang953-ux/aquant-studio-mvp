from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def evaluate_order(order: dict[str, Any], policy: dict[str, Any], used_value: float, used_count: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    symbol = order.get("symbol")
    source = order.get("source")
    value = float(order.get("quantity", 0)) * float(order.get("estimated_price", 0))

    if policy.get("kill_switch_enabled"):
        reasons.append("limited auto kill switch is enabled")
    if symbol not in policy.get("allowed_symbols", []):
        reasons.append(f"symbol is not allowed for limited automation: {symbol}")
    if source not in policy.get("allowed_sources", []):
        reasons.append(f"source is not allowed for limited automation: {source}")
    if policy.get("manual_approval_required", True) and not order.get("manual_approval"):
        reasons.append("manual approval is required for limited automation")
    if value > float(policy.get("max_order_value", 0)):
        reasons.append("order value exceeds limited automation max_order_value")
    if used_count + 1 > int(policy.get("max_daily_order_count", 0)):
        reasons.append("limited automation daily order count would be exceeded")
    if used_value + value > float(policy.get("max_daily_order_value", 0)):
        reasons.append("limited automation daily order value would be exceeded")

    return not reasons, reasons


def run_guard(orders_payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    approved = []
    rejected = []
    used_value = 0.0
    used_count = 0
    for order in orders_payload.get("approved_orders", []):
        accepted, reasons = evaluate_order(order, policy, used_value, used_count)
        value = float(order.get("quantity", 0)) * float(order.get("estimated_price", 0))
        if accepted:
            candidate = {
                **order,
                "automation_mode": "limited_auto_candidate",
                "automation_checked_at": now_iso(),
                "estimated_order_value": round(value, 6),
            }
            approved.append(candidate)
            used_value += value
            used_count += 1
        else:
            rejected.append({**order, "automation_reject_reasons": reasons})
    return {
        "ok": True,
        "mode": "limited_auto_guard",
        "live_submission_enabled": False,
        "generated_at": now_iso(),
        "candidate_orders": approved,
        "rejected_orders": rejected,
        "usage": {
            "candidate_count": used_count,
            "candidate_value": round(used_value, 6)
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant limited automation guard")
    parser.add_argument("--orders", default="manual_confirmation_module/output/stage8_manual_confirmation_result.json")
    parser.add_argument("--policy", default="automation_controls_module/configs/limited_auto_policy.json")
    parser.add_argument("--output", default="automation_controls_module/output/stage9_limited_auto_candidates.json")
    args = parser.parse_args()
    result = run_guard(read_json(Path(args.orders)), read_json(Path(args.policy)))
    write_json(Path(args.output), result)
    print(json.dumps({"ok": True, "candidates": len(result["candidate_orders"]), "rejected": len(result["rejected_orders"]), "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

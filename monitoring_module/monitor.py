from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_alert(alerts: list[dict[str, Any]], severity: str, code: str, message: str, payload: dict[str, Any] | None = None) -> None:
    alerts.append({"severity": severity, "code": code, "message": message, "payload": payload or {}})


def run_monitor(config: dict[str, Any]) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    paths = config["paths"]

    gateway = read_json(Path(paths["gateway_result"]))
    if gateway is None:
        add_alert(alerts, "warning", "gateway_result_missing", "gateway result file is missing")
    else:
        decision = gateway.get("decision", {})
        metrics["gateway_decision_status"] = decision.get("status")
        metrics["gateway_order_status"] = gateway.get("order", {}).get("status")
        if decision.get("status") == "rejected":
            add_alert(alerts, "warning", "gateway_rejected_order", "gateway rejected latest order", {"reasons": decision.get("reasons", [])})
        if gateway.get("order", {}).get("status") == "failed":
            add_alert(alerts, "critical", "gateway_failed_order", "gateway order failed")

    shadow = read_json(Path(paths["shadow_report"]))
    if shadow is None:
        add_alert(alerts, "warning", "shadow_report_missing", "shadow report file is missing")
    else:
        infeasible = [item for item in shadow.get("results", []) if not item.get("feasible")]
        metrics["shadow_order_count"] = len(shadow.get("results", []))
        metrics["shadow_infeasible_count"] = len(infeasible)
        if infeasible:
            add_alert(alerts, "info", "shadow_infeasible_orders", "some shadow orders are infeasible", {"count": len(infeasible)})

    candidates = read_json(Path(paths["limited_auto_candidates"]))
    if candidates is None:
        add_alert(alerts, "warning", "limited_auto_missing", "limited auto candidate file is missing")
    else:
        metrics["limited_auto_candidate_count"] = len(candidates.get("candidate_orders", []))
        metrics["limited_auto_rejected_count"] = len(candidates.get("rejected_orders", []))
        if candidates.get("rejected_orders"):
            add_alert(alerts, "warning", "limited_auto_rejections", "limited automation rejected orders")
        if candidates.get("live_submission_enabled"):
            add_alert(alerts, "critical", "live_submission_enabled", "live submission flag is unexpectedly enabled")

    account = read_json(Path(paths["read_only_account"]))
    if account is None:
        add_alert(alerts, "warning", "readonly_account_missing", "read-only account snapshot is missing")
    else:
        metrics["readonly_mode"] = account.get("mode")
        if account.get("mode") != "read_only":
            add_alert(alerts, "critical", "readonly_mode_invalid", "account sync is not in read_only mode")

    severity_order = {"info": 1, "warning": 2, "critical": 3}
    max_severity = max((severity_order[item["severity"]] for item in alerts), default=0)
    status = "critical" if max_severity >= 3 else "warning" if max_severity == 2 else "ok"
    return {
        "ok": status != "critical",
        "status": status,
        "generated_at": now_iso(),
        "metrics": metrics,
        "alerts": alerts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant live-readiness monitor")
    parser.add_argument("--config", default="monitoring_module/configs/monitoring_config.json")
    parser.add_argument("--output", default="monitoring_module/output/stage10_monitor_report.json")
    args = parser.parse_args()
    report = run_monitor(read_json(Path(args.config)) or {})
    write_json(Path(args.output), report)
    print(json.dumps({"ok": report["ok"], "status": report["status"], "alerts": len(report["alerts"]), "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

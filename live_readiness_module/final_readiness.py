from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_final_readiness(config: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: dict[str, Any] = {}

    gateway_config = read_json(ROOT / config["gateway_config"])
    monitor_report = read_json(ROOT / config["monitor_report"])
    audit_manifest = read_json(ROOT / config["audit_manifest"])
    limited_auto_policy = read_json(ROOT / config["limited_auto_policy"])

    evidence["gateway_live_trading_enabled"] = gateway_config.get("live_trading_enabled")
    evidence["gateway_policy"] = gateway_config.get("live_trading_policy", {})
    evidence["monitor_status"] = monitor_report.get("status")
    evidence["audit_ok"] = audit_manifest.get("ok")
    evidence["limited_auto_kill_switch"] = limited_auto_policy.get("kill_switch_enabled")

    if gateway_config.get("live_trading_enabled"):
        blockers.append("gateway live_trading_enabled must remain false until formal release approval")
    if gateway_config.get("live_trading_policy", {}).get("allow_real_broker_submit"):
        blockers.append("real broker submission flag must remain false before final approval")
    if monitor_report.get("status") == "critical":
        blockers.append("monitor report has critical alerts")
    if not audit_manifest.get("ok"):
        blockers.append("audit manifest has missing artifacts")

    required_external_confirmations = config.get("required_external_confirmations", [])
    for item in required_external_confirmations:
        if not item.get("confirmed"):
            blockers.append(f"external confirmation missing: {item['name']}")

    required_internal_controls = config.get("required_internal_controls", [])
    for item in required_internal_controls:
        if not item.get("ready"):
            warnings.append(f"internal control not production-ready: {item['name']}")

    final_status = "blocked_for_live_trading" if blockers else "ready_for_manual_release_review"
    return {
        "ok": not blockers,
        "final_status": final_status,
        "generated_at": now_iso(),
        "blockers": blockers,
        "warnings": warnings,
        "evidence": evidence,
        "next_required_action": "resolve blockers and rerun final readiness check" if blockers else "perform human release review",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AQuant final live readiness check")
    parser.add_argument("--config", default="live_readiness_module/configs/final_readiness_config.json")
    parser.add_argument("--output", default="live_readiness_module/output/stage12_final_readiness.json")
    args = parser.parse_args()
    report = check_final_readiness(read_json(Path(args.config)))
    write_json(Path(args.output), report)
    print(json.dumps({"ok": report["ok"], "final_status": report["final_status"], "blockers": len(report["blockers"]), "output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

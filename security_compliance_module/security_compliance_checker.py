from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    check_id: str
    status: str
    severity: str
    message: str
    evidence: str


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def add(results: list[CheckResult], check_id: str, ok: bool, severity: str, message: str, evidence: str) -> None:
    results.append(CheckResult(check_id, "pass" if ok else "fail", severity, message, evidence))


def run_checks(policy: dict[str, Any], gateway_config: dict[str, Any], gateway_output: Path, disclosure_path: Path, checklist_path: Path) -> dict[str, Any]:
    results: list[CheckResult] = []
    risk_limits = gateway_config.get("risk_limits", {})
    audit = gateway_config.get("audit", {})

    add(
        results,
        "LIVE_TRADING_DISABLED",
        gateway_config.get("live_trading_enabled") is False and policy.get("live_trading_allowed") is False,
        "critical",
        "实盘交易开关必须关闭",
        f"live_trading_enabled={gateway_config.get('live_trading_enabled')}, live_trading_allowed={policy.get('live_trading_allowed')}",
    )
    add(results, "SANDBOX_MODE", gateway_config.get("mode") == "sandbox", "critical", "当前阶段必须运行在 sandbox 模式", f"mode={gateway_config.get('mode')}")
    add(results, "AUDIT_ENABLED", audit.get("write_audit_log") is True, "high", "必须启用审计日志", f"write_audit_log={audit.get('write_audit_log')}")
    add(results, "ACCOUNT_STATE_ENABLED", audit.get("write_account_state") is True, "high", "必须写入账户状态", f"write_account_state={audit.get('write_account_state')}")
    add(results, "SHORT_SELL_REJECTED", risk_limits.get("reject_short_sell") is True, "high", "必须禁止裸卖空", f"reject_short_sell={risk_limits.get('reject_short_sell')}")
    add(results, "MAX_ORDER_VALUE_SET", isinstance(risk_limits.get("max_order_value"), (int, float)) and risk_limits["max_order_value"] > 0, "high", "必须设置单笔最大订单金额", f"max_order_value={risk_limits.get('max_order_value')}")
    add(results, "DAILY_ORDER_LIMIT_SET", isinstance(risk_limits.get("daily_order_limit"), int) and risk_limits["daily_order_limit"] > 0, "medium", "必须设置每日订单数量限制", f"daily_order_limit={risk_limits.get('daily_order_limit')}")
    add(results, "SYMBOL_WHITELIST_SET", bool(risk_limits.get("allowed_symbols")), "medium", "必须设置可交易标的白名单", f"allowed_symbols={risk_limits.get('allowed_symbols')}")

    audit_log = gateway_output / "audit_log.csv"
    account_state = gateway_output / "account_state.json"
    orders = gateway_output / "orders.csv"
    fills = gateway_output / "fills.csv"
    audit_rows = read_csv_rows(audit_log)
    order_rows = read_csv_rows(orders)
    fill_rows = read_csv_rows(fills)

    add(results, "AUDIT_LOG_EXISTS", audit_log.exists() and audit_log.stat().st_size > 0, "high", "审计日志文件必须存在且非空", str(audit_log))
    add(results, "ACCOUNT_STATE_EXISTS", account_state.exists() and account_state.stat().st_size > 0, "high", "账户状态文件必须存在且非空", str(account_state))
    add(results, "ORDER_LOG_EXISTS", orders.exists() and orders.stat().st_size > 0, "medium", "订单记录必须存在", str(orders))
    add(results, "FILL_LOG_EXISTS", fills.exists() and fills.stat().st_size > 0, "medium", "成交记录必须存在", str(fills))

    present_events = {row.get("event_type") for row in audit_rows}
    for event_type in policy.get("minimum_audit_events", []):
        add(results, f"AUDIT_EVENT_{event_type.upper()}", event_type in present_events, "medium", f"审计日志必须包含 {event_type}", f"present_events={sorted(present_events)}")

    rejected_orders = [row for row in order_rows if row.get("status") == "rejected"]
    add(results, "REJECTION_AUDITED", bool(rejected_orders), "medium", "必须至少验证并审计一条风控拒单", f"rejected_orders={len(rejected_orders)}")

    disclosure_text = disclosure_path.read_text(encoding="utf-8") if disclosure_path.exists() else ""
    for disclosure_id in policy.get("required_disclosures", []):
        keyword_map = {
            "backtest_not_future_performance": "历史表现不代表未来收益",
            "not_investment_advice": "不构成任何投资建议",
            "user_bears_trading_risk": "自行承担",
            "sandbox_not_real_trading": "不连接真实券商",
            "live_trading_requires_separate_approval": "单独审批",
        }
        keyword = keyword_map.get(disclosure_id, disclosure_id)
        add(results, f"DISCLOSURE_{disclosure_id.upper()}", keyword in disclosure_text, "medium", f"风险披露必须包含：{keyword}", str(disclosure_path))

    checklist_text = checklist_path.read_text(encoding="utf-8") if checklist_path.exists() else ""
    add(results, "LIVE_CHECKLIST_EXISTS", checklist_path.exists() and "当前项目不得进入实盘交易" in checklist_text, "high", "必须存在实盘上线前检查清单并明确当前不得实盘", str(checklist_path))

    blockers = policy.get("production_blockers", [])
    summary = {
        "policy_id": policy["policy_id"],
        "environment": policy["environment"],
        "overall_status": "blocked_for_live_trading",
        "pass_count": sum(1 for item in results if item.status == "pass"),
        "fail_count": sum(1 for item in results if item.status == "fail"),
        "production_blockers": blockers,
        "orders_checked": len(order_rows),
        "fills_checked": len(fill_rows),
        "audit_events_checked": len(audit_rows),
    }
    return {"summary": summary, "checks": [asdict(item) for item in results]}


def render_html(report: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{check['check_id']}</td><td>{check['status']}</td><td>{check['severity']}</td>"
        f"<td>{check['message']}</td><td>{check['evidence']}</td>"
        "</tr>"
        for check in report["checks"]
    )
    blockers = "".join(f"<li>{item}</li>" for item in report["summary"]["production_blockers"])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>安全与合规检查报告</title>
  <style>
    body {{ margin:0; background:#f5f7f8; color:#17202a; font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif; }}
    header {{ background:#fff; border-bottom:1px solid #dfe5e8; padding:22px 28px; }}
    h1 {{ margin:0; font-size:22px; }}
    .sub {{ color:#667085; margin-top:8px; }}
    main {{ padding:24px 28px; display:grid; gap:20px; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:14px; }}
    .card {{ background:#fff; border:1px solid #dfe5e8; border-radius:8px; padding:15px; }}
    .card span {{ display:block; color:#667085; font-size:13px; }}
    .card strong {{ display:block; margin-top:8px; font-size:22px; }}
    .blocked strong {{ color:#c2410c; }}
    section {{ background:#fff; border:1px solid #dfe5e8; border-radius:8px; overflow:hidden; }}
    h2 {{ margin:0; padding:16px 18px; font-size:16px; border-bottom:1px solid #dfe5e8; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:11px 13px; border-bottom:1px solid #dfe5e8; text-align:left; vertical-align:top; }}
    th {{ background:#fafafa; color:#667085; }}
    .wrap {{ overflow-x:auto; }}
    li {{ margin:8px 0; }}
  </style>
</head>
<body>
  <header>
    <h1>安全与合规检查报告</h1>
    <div class="sub">策略平台 MVP / 沙箱阶段 / 当前不得进入实盘交易</div>
  </header>
  <main>
    <div class="cards">
      <div class="card blocked"><span>实盘状态</span><strong>{report['summary']['overall_status']}</strong></div>
      <div class="card"><span>通过检查</span><strong>{report['summary']['pass_count']}</strong></div>
      <div class="card"><span>失败检查</span><strong>{report['summary']['fail_count']}</strong></div>
      <div class="card"><span>审计事件</span><strong>{report['summary']['audit_events_checked']}</strong></div>
    </div>
    <section>
      <h2>生产阻断项</h2>
      <ul>{blockers}</ul>
    </section>
    <section>
      <h2>检查明细</h2>
      <div class="wrap"><table><thead><tr><th>检查项</th><th>状态</th><th>严重性</th><th>说明</th><th>证据</th></tr></thead><tbody>{rows}</tbody></table></div>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AQuant security and compliance checks")
    parser.add_argument("--policy", default="security_compliance_module/configs/security_policy.json")
    parser.add_argument("--gateway-config", default="trading_gateway_module/configs/sandbox_gateway.json")
    parser.add_argument("--gateway-output", default="trading_gateway_module/output/sandbox")
    parser.add_argument("--disclosure", default="security_compliance_module/disclosures/risk_disclosure_zh.md")
    parser.add_argument("--checklist", default="security_compliance_module/live-readiness-checklist.md")
    parser.add_argument("--output-dir", default="security_compliance_module/output")
    args = parser.parse_args()

    report = run_checks(
        read_json(Path(args.policy)),
        read_json(Path(args.gateway_config)),
        Path(args.gateway_output),
        Path(args.disclosure),
        Path(args.checklist),
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "security_compliance_report.json", report)
    (output_dir / "security_compliance_report.html").write_text(render_html(report), encoding="utf-8")
    print(json.dumps({"ok": True, "output_dir": str(output_dir), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

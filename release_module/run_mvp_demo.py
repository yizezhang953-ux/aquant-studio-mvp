from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def run_step(name: str, command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return {
        "name": name,
        "ok": completed.returncode == 0,
        "return_code": completed.returncode,
        "stdout": completed.stdout.strip()[-1200:],
        "stderr": completed.stderr.strip()[-1200:],
    }


def file_check(path: str) -> dict[str, Any]:
    target = ROOT / path
    return {
        "name": f"file exists: {path}",
        "ok": target.exists() and target.stat().st_size >= 0,
        "path": path,
        "size": target.stat().st_size if target.exists() else None,
    }


def main() -> None:
    steps = [
        run_step(
            "data health",
            [str(PYTHON), "data_module/market_data.py", "--db", "data_module/market_data.sqlite", "health"],
        ),
        run_step(
            "strategy validation",
            [
                str(PYTHON),
                "strategy_module/strategy_validator.py",
                "strategy_module/samples/price_breakout_demo_strategy.json",
                "--db",
                "data_module/market_data.sqlite",
            ],
        ),
        run_step(
            "backtest smoke",
            [
                str(PYTHON),
                "backtest_module/backtest_engine.py",
                "strategy_module/samples/price_breakout_demo_strategy.json",
                "--db",
                "data_module/market_data.sqlite",
                "--output-dir",
                "release_module/output/backtest_smoke",
            ],
        ),
        run_step(
            "template validation",
            [str(PYTHON), "template_module/template_manager.py", "validate-all", "--db", "data_module/market_data.sqlite"],
        ),
        run_step(
            "security compliance",
            [str(PYTHON), "security_compliance_module/security_compliance_checker.py", "--output-dir", "release_module/output/security_check"],
        ),
    ]
    files = [
        file_check("release_module/index.html"),
        file_check("PROJECT_OVERVIEW.md"),
        file_check("visualization_module/output/price_breakout_report.html"),
        file_check("optimization_module/output/price_breakout_grid/ranking.html"),
        file_check("simulation_module/output/price_breakout_paper/paper_trading_report.html"),
        file_check("security_compliance_module/output/security_compliance_report.html"),
    ]
    ok = all(step["ok"] for step in steps) and all(item["ok"] for item in files)
    result = {"ok": ok, "steps": steps, "files": files}
    output = ROOT / "release_module" / "output" / "mvp_demo_result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": ok, "result": str(output)}, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

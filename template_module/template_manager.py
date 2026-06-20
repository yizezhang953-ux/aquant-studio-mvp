from __future__ import annotations

import argparse
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_DIR = ROOT / "template_module" / "templates"
DEFAULT_OUTPUT_DIR = ROOT / "template_module" / "generated_strategies"
PYTHON = Path(sys.executable)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_index(template_dir: Path) -> dict[str, Any]:
    return read_json(template_dir / "index.json")


def get_template_meta(template_dir: Path, template_id: str) -> dict[str, Any]:
    index = load_index(template_dir)
    for item in index["templates"]:
        if item["template_id"] == template_id:
            return item
    raise ValueError(f"template not found: {template_id}")


def instantiate_template(
    template_dir: Path,
    template_id: str,
    symbol: str | None,
    frequency: str | None,
    output_dir: Path,
) -> Path:
    meta = get_template_meta(template_dir, template_id)
    strategy = deepcopy(read_json(template_dir / meta["file"]))
    final_symbol = symbol or meta["default_symbol"]
    final_frequency = frequency or meta["default_frequency"]
    strategy["strategy_id"] = f"{template_id}_{final_symbol.replace('.', '_')}_{final_frequency}"
    strategy["universe"]["symbols"] = [final_symbol]
    strategy["data"]["frequency"] = final_frequency
    strategy["metadata"]["source_template_id"] = template_id
    output_path = output_dir / f"{strategy['strategy_id']}.json"
    write_json(output_path, strategy)
    return output_path


def run_command(args: list[str], cwd: Path) -> tuple[int, str]:
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    output = completed.stdout.strip()
    if completed.stderr.strip():
        output = f"{output}\n{completed.stderr.strip()}".strip()
    return completed.returncode, output


def validate_strategy(strategy_path: Path, db_path: Path) -> dict[str, Any]:
    code, output = run_command(
        [
            str(PYTHON),
            "strategy_module/strategy_validator.py",
            str(strategy_path),
            "--db",
            str(db_path),
        ],
        ROOT,
    )
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = {"ok": False, "errors": [output], "warnings": []}
    parsed["return_code"] = code
    return parsed


def backtest_strategy(strategy_path: Path, db_path: Path, output_dir: Path) -> dict[str, Any]:
    code, output = run_command(
        [
            str(PYTHON),
            "backtest_module/backtest_engine.py",
            str(strategy_path),
            "--db",
            str(db_path),
            "--output-dir",
            str(output_dir),
        ],
        ROOT,
    )
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = {"ok": False, "error": output}
    parsed["return_code"] = code
    return parsed


def validate_all(template_dir: Path, db_path: Path) -> list[dict[str, Any]]:
    index = load_index(template_dir)
    results = []
    for item in index["templates"]:
        path = template_dir / item["file"]
        result = validate_strategy(path, db_path)
        results.append({"template_id": item["template_id"], "file": item["file"], "validation": result})
    return results


def backtest_all(template_dir: Path, db_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    index = load_index(template_dir)
    results = []
    for item in index["templates"]:
        strategy_path = template_dir / item["file"]
        template_output = output_dir / item["template_id"]
        validation = validate_strategy(strategy_path, db_path)
        if not validation.get("ok"):
            results.append({"template_id": item["template_id"], "validation": validation, "backtest": None})
            continue
        backtest = backtest_strategy(strategy_path, db_path, template_output)
        results.append({"template_id": item["template_id"], "validation": validation, "backtest": backtest})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage AQuant strategy templates")
    parser.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("template_id")
    create_parser.add_argument("--symbol")
    create_parser.add_argument("--frequency")
    create_parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))

    validate_parser = subparsers.add_parser("validate-all")
    validate_parser.add_argument("--db", default=str(ROOT / "data_module" / "market_data.sqlite"))

    backtest_parser = subparsers.add_parser("backtest-all")
    backtest_parser.add_argument("--db", default=str(ROOT / "data_module" / "market_data.sqlite"))
    backtest_parser.add_argument("--output-dir", default=str(ROOT / "template_module" / "output"))

    args = parser.parse_args()
    template_dir = Path(args.template_dir)

    if args.command == "list":
        print(json.dumps(load_index(template_dir), ensure_ascii=False, indent=2))
    elif args.command == "create":
        path = instantiate_template(
            template_dir,
            args.template_id,
            args.symbol,
            args.frequency,
            Path(args.output_dir),
        )
        print(json.dumps({"ok": True, "strategy_path": str(path)}, ensure_ascii=False, indent=2))
    elif args.command == "validate-all":
        print(json.dumps(validate_all(template_dir, Path(args.db)), ensure_ascii=False, indent=2))
    elif args.command == "backtest-all":
        print(json.dumps(backtest_all(template_dir, Path(args.db), Path(args.output_dir)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

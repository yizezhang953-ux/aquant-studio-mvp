from __future__ import annotations

import argparse
import csv
import json
from copy import deepcopy
from itertools import product
from pathlib import Path
from typing import Any

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backtest_module"))

from backtest_engine import load_bars, run_backtest, write_report  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_by_path(obj: dict[str, Any], path: str, value: Any) -> None:
    current: Any = obj
    parts = path.split(".")
    for part in parts[:-1]:
        if part.isdigit():
            current = current[int(part)]
        else:
            current = current[part]
    last = parts[-1]
    if last.isdigit():
        current[int(last)] = value
    else:
        current[last] = value


def combinations(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = [param["name"] for param in parameters]
    value_sets = [param["values"] for param in parameters]
    return [dict(zip(names, values)) for values in product(*value_sets)]


def apply_params(strategy: dict[str, Any], parameters: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    candidate = deepcopy(strategy)
    suffix = "_".join(f"{name}_{values[name]}" for name in values)
    candidate["strategy_id"] = f"{strategy['strategy_id']}_{suffix}".replace(".", "_")
    candidate.setdefault("metadata", {})
    candidate["metadata"]["optimization_params"] = values
    for param in parameters:
        set_by_path(candidate, param["path"], values[param["name"]])
    return candidate


def sort_key(row: dict[str, Any], objective: dict[str, Any]) -> tuple[Any, ...]:
    keys = []
    primary = objective["primary_metric"]
    primary_value = row.get(primary)
    keys.append(primary_value if objective.get("direction") == "min" else -primary_value)
    for breaker in objective.get("tie_breakers", []):
        value = row.get(breaker["metric"])
        keys.append(value if breaker.get("direction") == "min" else -value)
    return tuple(keys)


def flatten_result(rank: int, params: dict[str, Any], report: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    metrics = report["metrics"]
    row = {
        "rank": rank,
        "strategy_id": report["strategy_id"],
        "symbol": report["symbol"],
        "frequency": report["frequency"],
        "report_dir": str(output_dir),
    }
    row.update(params)
    row.update(metrics)
    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def format_pct(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def format_num(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.4f}"


def render_html(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    best = rows[0] if rows else {}
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{row['rank']}</td>"
            f"<td>{row.get('entry_threshold')}</td>"
            f"<td>{row.get('exit_threshold')}</td>"
            f"<td>{row.get('order_size')}</td>"
            f"<td>{format_pct(row.get('total_return'))}</td>"
            f"<td>{format_pct(row.get('max_drawdown'))}</td>"
            f"<td>{row.get('trade_count')}</td>"
            f"<td>{format_num(row.get('sharpe'))}</td>"
            "</tr>"
        )
    table_rows = "\n".join(body_rows)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{summary['name']} - 参数优化</title>
  <style>
    :root {{
      --bg: #f5f7f8;
      --panel: #fff;
      --line: #dfe5e8;
      --text: #17202a;
      --muted: #667085;
      --brand: #0f766e;
      --soft: #e5f3ef;
      --bad: #c2410c;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    header {{ background: var(--panel); border-bottom: 1px solid var(--line); padding: 22px 28px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    .sub {{ color: var(--muted); margin-top: 8px; }}
    main {{ padding: 24px 28px; display: grid; gap: 20px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 14px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 15px; }}
    .card span {{ display: block; color: var(--muted); font-size: 13px; }}
    .card strong {{ display: block; margin-top: 8px; font-size: 24px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    .panel-head {{ padding: 16px 18px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; }}
    .panel-head h2 {{ margin: 0; font-size: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    th {{ color: var(--muted); background: #fafafa; }}
    .table-wrap {{ overflow-x: auto; }}
    .badge {{ display: inline-flex; align-items: center; padding: 3px 9px; border-radius: 999px; background: var(--soft); color: var(--brand); font-size: 13px; }}
    @media (max-width: 760px) {{ .cards {{ grid-template-columns: 1fr 1fr; }} main {{ padding: 16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{summary['name']}</h1>
    <div class="sub">优化 ID：{summary['optimization_id']} · 参数组合：{summary['candidate_count']} · 目标：{summary['objective']['primary_metric']}</div>
  </header>
  <main>
    <section class="cards">
      <div class="card"><span>最佳总收益率</span><strong>{format_pct(best.get('total_return'))}</strong></div>
      <div class="card"><span>最佳最大回撤</span><strong>{format_pct(best.get('max_drawdown'))}</strong></div>
      <div class="card"><span>最佳交易次数</span><strong>{best.get('trade_count', '-')}</strong></div>
      <div class="card"><span>最佳参数</span><strong>{best.get('entry_threshold', '-')}/{best.get('exit_threshold', '-')}</strong></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>参数排行榜</h2><span class="badge">按目标排序</span></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名</th><th>买入阈值</th><th>卖出阈值</th><th>仓位</th><th>总收益率</th><th>最大回撤</th><th>交易次数</th><th>夏普</th>
            </tr>
          </thead>
          <tbody>{table_rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def run_optimization(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = read_json(config_path)
    base_strategy = read_json(ROOT / config["base_strategy"])
    db_path = ROOT / config["db_path"]
    parameters = config["parameters"]
    candidate_values = combinations(parameters)
    raw_results: list[dict[str, Any]] = []

    for index, values in enumerate(candidate_values, start=1):
        strategy = apply_params(base_strategy, parameters, values)
        candidate_dir = output_dir / "candidates" / f"candidate_{index:03d}"
        write_json(candidate_dir / "strategy.json", strategy)
        bars = load_bars(db_path, strategy)
        report = run_backtest(strategy, bars)
        write_report(report, candidate_dir)
        raw_results.append({"params": values, "report": report, "output_dir": candidate_dir})

    rows = [
        flatten_result(index, item["params"], item["report"], item["output_dir"])
        for index, item in enumerate(raw_results, start=1)
    ]
    rows.sort(key=lambda row: sort_key(row, config["objective"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    summary = {
        "optimization_id": config["optimization_id"],
        "name": config["name"],
        "objective": config["objective"],
        "candidate_count": len(rows),
        "best": rows[0] if rows else None,
        "results": rows,
    }
    write_json(output_dir / "summary.json", summary)
    write_csv(output_dir / "ranking.csv", rows)
    (output_dir / "ranking.html").write_text(render_html(summary, rows), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AQuant parameter optimization")
    parser.add_argument("config")
    parser.add_argument("--output-dir", default="optimization_module/output/price_breakout_grid")
    args = parser.parse_args()
    summary = run_optimization(Path(args.config), Path(args.output_dir))
    print(json.dumps({"ok": True, "output_dir": args.output_dir, "best": summary["best"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

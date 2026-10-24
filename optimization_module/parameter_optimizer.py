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

from backtest_engine import load_bars, load_market_context, run_backtest, write_report  # noqa: E402

DEFAULT_VALIDATION = {"method": "holdout", "train_ratio": 0.7}


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


def _key(value: Any, direction: str | None) -> tuple[int, float]:
    if value is None:
        return (1, 0.0)  # missing metrics (e.g. Sharpe with no trades) rank last
    return (0, float(value) if direction == "min" else -float(value))


def sort_key(row: dict[str, Any], objective: dict[str, Any]) -> tuple[Any, ...]:
    keys = [_key(row.get(objective["primary_metric"]), objective.get("direction"))]
    for breaker in objective.get("tie_breakers", []):
        keys.append(_key(row.get(breaker["metric"]), breaker.get("direction")))
    return tuple(keys)


def split_windows(bars: list, start: str, end: str, validation: dict[str, Any]) -> list[dict[str, str]]:
    """Train/test windows inside [start, end].

    holdout      : first ``train_ratio`` of the bars to train, the rest to test (or ``split_date``).
    walk_forward : ``folds`` sequential test windows; each trains on all bars before it (anchored).
    """
    days = sorted({bar.trade_time[:10] for bar in bars if start <= bar.trade_time[:10] <= end})
    if len(days) < 4:
        raise ValueError("not enough bars for an out-of-sample split; load more history")
    method = validation.get("method", "holdout")
    if method == "holdout":
        if validation.get("split_date"):
            train_days = [d for d in days if d <= validation["split_date"]]
            test_days = [d for d in days if d > validation["split_date"]]
        else:
            cut = max(2, min(len(days) - 2, int(len(days) * float(validation.get("train_ratio", 0.7)))))
            train_days, test_days = days[:cut], days[cut:]
        if not train_days or not test_days:
            raise ValueError("split leaves an empty train or test window")
        return [{"train_start": train_days[0], "train_end": train_days[-1], "test_start": test_days[0], "test_end": test_days[-1]}]
    if method == "walk_forward":
        folds = int(validation.get("folds", 4))
        first_test = int(len(days) * float(validation.get("initial_train_ratio", 0.5)))
        size = max(1, (len(days) - first_test) // folds)
        windows = []
        for fold in range(folds):
            a = first_test + fold * size
            b = len(days) - 1 if fold == folds - 1 else a + size - 1
            if a >= len(days) or a < 2:
                break
            windows.append({"train_start": days[0], "train_end": days[a - 1], "test_start": days[a], "test_end": days[b]})
        return windows
    raise ValueError(f"unsupported validation method: {method}")


def with_window(strategy: dict[str, Any], start: str, end: str) -> dict[str, Any]:
    candidate = deepcopy(strategy)
    candidate["data"]["start_date"] = start
    candidate["data"]["end_date"] = end
    return candidate


def spearman(xs: list[float | None], ys: list[float | None]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out

    rx, ry = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(cov / var, 4) if var else None


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
    validation = summary.get("validation", {})
    corr = validation.get("train_test_rank_correlation")
    overfit = "⚠ 最优参数在验证期低于中位数，疑似过拟合" if validation.get("overfit_warning") else "未见明显过拟合信号"
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{row['rank']}</td>"
            f"<td>{row.get('entry_threshold')}</td>"
            f"<td>{row.get('exit_threshold')}</td>"
            f"<td>{row.get('order_size')}</td>"
            f"<td>{format_pct(row.get('train_total_return'))}</td>"
            f"<td>{format_pct(row.get('test_total_return'))}</td>"
            f"<td>{format_pct(row.get('test_max_drawdown'))}</td>"
            f"<td>{row.get('test_trade_count')}</td>"
            f"<td>{format_num(row.get('test_sharpe'))}</td>"
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
      <div class="card"><span>最佳参数 训练期收益</span><strong>{format_pct(best.get('train_total_return'))}</strong></div>
      <div class="card"><span>最佳参数 验证期收益</span><strong>{format_pct(best.get('test_total_return'))}</strong></div>
      <div class="card"><span>训练/验证排名相关</span><strong>{format_num(corr)}</strong></div>
      <div class="card"><span>最佳参数</span><strong>{best.get('entry_threshold', '-')}/{best.get('exit_threshold', '-')}</strong></div>
    </section>
    <section class="panel"><div class="panel-head"><h2>样本外检验</h2><span class="badge">{validation.get('method', '-')}</span></div>
      <div style="padding:14px 18px;color:var(--muted)">排名只用训练期；{overfit}。窗口：{'; '.join(w['train_start'] + '~' + w['train_end'] + ' → ' + w['test_start'] + '~' + w['test_end'] for w in validation.get('windows', []))}</div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>参数排行榜</h2><span class="badge">按目标排序</span></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名(按训练期)</th><th>买入阈值</th><th>卖出阈值</th><th>仓位</th><th>训练期收益</th><th>验证期收益</th><th>验证期回撤</th><th>验证期交易</th><th>验证期夏普</th>
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
    """Grid search ranked on the TRAIN window(s) only; TEST windows report out-of-sample results."""
    config = read_json(config_path)
    base_strategy = read_json(ROOT / config["base_strategy"])
    db_path = ROOT / config["db_path"]
    parameters = config["parameters"]
    objective = config["objective"]
    validation = {**DEFAULT_VALIDATION, **config.get("validation", {})}
    candidate_values = combinations(parameters)

    start, end = base_strategy["data"]["start_date"], base_strategy["data"]["end_date"]
    all_bars = load_bars(db_path, base_strategy, warmup_bars=400)  # loaded once, shared by every candidate
    context = load_market_context(db_path, base_strategy)
    windows = split_windows(all_bars, start, end, validation)
    metric = objective["primary_metric"]

    raw_results: list[dict[str, Any]] = []
    for index, values in enumerate(candidate_values, start=1):
        strategy = apply_params(base_strategy, parameters, values)
        candidate_dir = output_dir / "candidates" / f"candidate_{index:03d}"
        write_json(candidate_dir / "strategy.json", strategy)
        train_metrics, test_metrics = [], []
        for window in windows:
            train = run_backtest(with_window(strategy, window["train_start"], window["train_end"]), all_bars, context)
            test = run_backtest(with_window(strategy, window["test_start"], window["test_end"]), all_bars, context)
            train_metrics.append(train["metrics"])
            test_metrics.append(test["metrics"])
        full = run_backtest(strategy, all_bars, context)
        write_report(full, candidate_dir)
        raw_results.append({"params": values, "report": full, "output_dir": candidate_dir,
                            "train": train_metrics, "test": test_metrics})

    def mean_metric(items: list[dict[str, Any]], key: str) -> float | None:
        values = [item.get(key) for item in items if isinstance(item.get(key), (int, float))]
        return round(sum(values) / len(values), 6) if values else None

    metric_keys = [k for k, v in raw_results[0]["train"][0].items() if isinstance(v, (int, float))] if raw_results else []
    rows = []
    for item in raw_results:
        row = flatten_result(0, item["params"], item["report"], item["output_dir"])
        # Full-period metrics include the test window: keep them under full_* so nothing ranks on them.
        for key in list(item["report"]["metrics"]):
            row.pop(key, None)
            row[f"full_{key}"] = item["report"]["metrics"][key]
        for key in metric_keys:
            row[f"train_{key}"] = mean_metric(item["train"], key)
            row[f"test_{key}"] = mean_metric(item["test"], key)
        rows.append(row)

    def train_objective_for(prefix_metrics: dict[str, Any]) -> dict[str, Any]:
        return {**objective, "primary_metric": f"train_{metric}",
                "tie_breakers": [{**b, "metric": f"train_{b['metric']}"} for b in objective.get("tie_breakers", [])]}

    if metric not in metric_keys:
        raise ValueError(f"objective metric {metric} is not a numeric backtest metric")
    train_objective = train_objective_for({})
    rows.sort(key=lambda row: sort_key(row, train_objective))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    # Walk-forward: choose the best parameters on each fold's own train window and score them on
    # that fold's test window only — the honest out-of-sample estimate.
    fold_selection = []
    for fold, window in enumerate(windows):
        candidates = [
            {"params": item["params"], f"train_{metric}": item["train"][fold].get(metric),
             **{f"train_{b['metric']}": item["train"][fold].get(b["metric"]) for b in objective.get("tie_breakers", [])},
             "test": item["test"][fold]}
            for item in raw_results
        ]
        candidates.sort(key=lambda c: sort_key(c, train_objective))
        chosen = candidates[0]
        fold_selection.append({**window, "fold": fold + 1, "params": chosen["params"],
                               f"train_{metric}": chosen[f"train_{metric}"], f"test_{metric}": chosen["test"].get(metric)})

    test_values = [row.get(f"test_{metric}") for row in rows]
    known = sorted(v for v in test_values if v is not None)
    median_test = known[len(known) // 2] if known else None
    best = rows[0] if rows else None
    validation_summary = {
        **validation,
        "windows": windows,
        "ranked_on": train_objective["primary_metric"],
        "train_test_rank_correlation": spearman([r.get(f"train_{metric}") for r in rows], test_values),
        "fold_selection": fold_selection,
        "out_of_sample_mean": (round(sum(f[f"test_{metric}"] for f in fold_selection if f[f"test_{metric}"] is not None)
                                     / max(1, sum(1 for f in fold_selection if f[f"test_{metric}"] is not None)), 6)
                               if fold_selection else None),
        "best_test_value": best.get(f"test_{metric}") if best else None,
        "median_test_value": median_test,
        "overfit_warning": bool(best and median_test is not None and best.get(f"test_{metric}") is not None
                                and best[f"test_{metric}"] < median_test),
        "note": "Ranking uses train windows only (full_* columns include the test window and are for reference). "
                "out_of_sample_mean scores, per fold, the parameters chosen on that fold's train window. A low or "
                "negative train/test rank correlation means the in-sample ranking does not carry over.",
    }
    summary = {
        "optimization_id": config["optimization_id"],
        "name": config["name"],
        "objective": objective,
        "candidate_count": len(rows),
        "validation": validation_summary,
        "best": best,
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

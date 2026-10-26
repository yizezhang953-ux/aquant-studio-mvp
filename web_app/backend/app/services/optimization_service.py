"""Parameter optimization for the web app: grid search ranked on a train window, then checked on
a later test window the ranking never saw, so a result that only comes from tuning shows up."""
from __future__ import annotations

import copy
from itertools import product
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.services.backtest_service import BacktestInputError, no_data_message
from app.services.market_data_access import load_engine_bars, load_engine_context
from app.services.strategy_service import validate_strategy_payload

from backtest_engine import required_warmup_bars, run_backtest  # noqa: E402  (path set up by market_data_access)
from optimization_module.parameter_optimizer import set_by_path, spearman, split_windows, with_window  # noqa: E402

MAX_CANDIDATES = 200
MAX_RUNS = 1200
WINDOW_METRICS = ("total_return", "benchmark_return", "annualized_return", "max_drawdown", "sharpe",
                  "win_rate", "trade_count")
OBJECTIVES = {
    "total_return": "max",
    "annualized_return": "max",
    "sharpe": "max",
    "win_rate": "max",
    "max_drawdown": "min",
}


class OptimizationInputError(BacktestInputError):
    pass


def get_by_path(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        current = current[int(part)] if part.isdigit() else current[part]
    return current


def window_metrics(strategy: dict[str, Any], bars: list, context: Any, start: str, end: str) -> dict[str, Any]:
    report = run_backtest(with_window(strategy, start, end), bars, context)
    metrics = report.get("metrics", {})
    return {key: metrics.get(key) for key in WINDOW_METRICS}


def combine(folds: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean of each metric across folds; trade counts add up."""
    out: dict[str, Any] = {}
    for key in WINDOW_METRICS:
        values = [f[key] for f in folds if isinstance(f.get(key), (int, float))]
        if key == "trade_count":
            out[key] = int(sum(values))
        else:
            out[key] = round(sum(values) / len(values), 6) if values else None
    return out


def rank_key(metrics: dict[str, Any], metric: str) -> tuple:
    """Best first by the objective, then by smaller drawdown; missing values rank last."""
    def key(value: Any, direction: str) -> tuple[int, float]:
        if value is None:
            return (1, 0.0)
        return (0, float(value) if direction == "min" else -float(value))
    return (key(metrics.get(metric), OBJECTIVES[metric]), key(metrics.get("max_drawdown"), "min"))


def verdict(best: dict[str, Any], rows: list[dict[str, Any]], metric: str, correlation: float | None,
            out_of_sample: float | None) -> dict[str, Any]:
    """Plain-language call on whether the best train result holds up on the unseen window."""
    better = (lambda a, b: a < b) if OBJECTIVES[metric] == "min" else (lambda a, b: a > b)
    tests = [r["test"].get(metric) for r in rows if r["test"].get(metric) is not None]
    median_test = median(tests) if tests else None
    best_test = best["test"].get(metric)
    reasons: list[str] = []
    level = "good"
    if best_test is None:
        level = "overfit"
        reasons.append("最优参数在检验段没有可用结果（可能一笔交易都没有）。")
    else:
        if median_test is not None and better(median_test, best_test):
            level = "overfit"
            reasons.append("训练段第一名的参数，到了检验段还不如一半的参数组合。")
        if correlation is not None and correlation < 0:
            level = "overfit"
            reasons.append("训练段排名和检验段排名是反的：训练段越好的参数，检验段反而越差。")
        elif correlation is not None and correlation < 0.3 and level == "good":
            level = "caution"
            reasons.append("训练段排名和检验段排名关系很弱，参数好坏有很大运气成分。")
        if metric in ("total_return", "annualized_return", "sharpe") and best_test <= 0 and level == "good":
            level = "caution"
            reasons.append("最优参数在检验段没有赚钱。")
        if (best["test"].get("trade_count") or 0) < 3 and level == "good":
            level = "caution"
            reasons.append("检验段交易次数太少（少于 3 笔），结论不可靠。")
    if level == "good":
        reasons.append("训练段选出的参数在检验段依然靠前，没有发现明显的「调参调出来」迹象。")
    if out_of_sample is not None and correlation is None:
        reasons.append("参数组合太少，无法计算排名相关性。")
    return {"level": level, "reasons": reasons, "median_test_value": median_test, "best_test_value": best_test}


def optimize_strategy(db: Session, strategy: dict[str, Any], parameters: list[dict[str, Any]],
                      metric: str, validation: dict[str, Any]) -> dict[str, Any]:
    if metric not in OBJECTIVES:
        raise OptimizationInputError(f"不支持的优化目标：{metric}")
    base_check = validate_strategy_payload(strategy)
    if not base_check["ok"]:
        raise OptimizationInputError("strategy is invalid", base_check["errors"])
    if not parameters:
        raise OptimizationInputError("至少选择一个要优化的参数")
    for param in parameters:
        try:
            current = get_by_path(strategy, param["path"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise OptimizationInputError(f"策略里没有参数 {param['label']}") from None
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise OptimizationInputError(f"{param['label']} 不是数值参数")
        if not param["values"]:
            raise OptimizationInputError(f"{param['label']} 没有填要试的取值")
    grid = list(product(*(list(dict.fromkeys(p["values"])) for p in parameters)))
    if len(grid) > MAX_CANDIDATES:
        raise OptimizationInputError(f"一共 {len(grid)} 组参数，一次最多 {MAX_CANDIDATES} 组，请减少取值")

    candidates = []
    for values in grid:
        candidate = copy.deepcopy(strategy)
        for param, value in zip(parameters, values):
            set_by_path(candidate, param["path"], value)
        candidates.append((values, candidate))

    warmup = max(required_warmup_bars(c) for _, c in candidates)
    bars = load_engine_bars(db, strategy, warmup_bars=warmup)
    start, end = strategy["data"]["start_date"], strategy["data"]["end_date"]
    if not any(bar.trade_time[:10] >= start for bar in bars):
        raise OptimizationInputError(no_data_message(db, strategy))
    try:
        windows = split_windows(bars, start, end, validation)
    except ValueError as exc:
        raise OptimizationInputError("行情太少，无法切分训练段和检验段，请拉长回测区间") from exc
    if not windows:
        raise OptimizationInputError("行情太少，无法切分训练段和检验段，请拉长回测区间")
    if len(grid) * len(windows) * 2 > MAX_RUNS:
        raise OptimizationInputError(f"参数组合 × 检验段太多（要跑 {len(grid) * len(windows) * 2} 次回测），请减少取值或折数")
    context = load_engine_context(db, strategy)

    current_values = tuple(get_by_path(strategy, p["path"]) for p in parameters)
    rows: list[dict[str, Any]] = []
    for values, candidate in candidates:
        row: dict[str, Any] = {"values": list(values), "is_current": tuple(values) == current_values,
                               "ok": False, "error": None, "train": {}, "test": {}, "folds": []}
        check = validate_strategy_payload(candidate)
        if not check["ok"]:
            row["error"] = "；".join(check["errors"])
            rows.append(row)
            continue
        try:
            folds = [{"train": window_metrics(candidate, bars, context, w["train_start"], w["train_end"]),
                      "test": window_metrics(candidate, bars, context, w["test_start"], w["test_end"])}
                     for w in windows]
        except ValueError as exc:
            row["error"] = str(exc)
            rows.append(row)
            continue
        row.update(ok=True, folds=folds, train=combine([f["train"] for f in folds]),
                   test=combine([f["test"] for f in folds]))
        rows.append(row)

    done = sorted((r for r in rows if r["ok"]), key=lambda r: rank_key(r["train"], metric))
    for rank, row in enumerate(done, start=1):
        row["rank"] = rank
    failed = [r for r in rows if not r["ok"]]
    if not done:
        raise OptimizationInputError("所有参数组合都没跑成功：" + (failed[0]["error"] or ""))

    # Walk-forward: pick the best on each fold's own train window, score it on that fold's test window.
    fold_selection = []
    for index, window in enumerate(windows):
        chosen = min(done, key=lambda r: rank_key(r["folds"][index]["train"], metric))
        fold_selection.append({**window, "fold": index + 1, "values": chosen["values"],
                               "train_value": chosen["folds"][index]["train"].get(metric),
                               "test_value": chosen["folds"][index]["test"].get(metric)})
    oos = [f["test_value"] for f in fold_selection if f["test_value"] is not None]
    out_of_sample = round(sum(oos) / len(oos), 6) if oos else None
    correlation = spearman([r["train"].get(metric) for r in done], [r["test"].get(metric) for r in done])
    current = next((r for r in done if r["is_current"]), None)
    for row in done:
        row.pop("folds")
    return {
        "metric": metric,
        "direction": OBJECTIVES[metric],
        "parameters": [{"path": p["path"], "label": p["label"]} for p in parameters],
        "windows": windows,
        "validation": validation,
        "rows": done + [{k: v for k, v in r.items() if k != "folds"} for r in failed],
        "best": done[0],
        "current": current,
        "fold_selection": fold_selection,
        "out_of_sample_mean": out_of_sample,
        "rank_correlation": correlation,
        "verdict": verdict(done[0], done, metric, correlation, out_of_sample),
        "candidate_count": len(rows),
        "failed_count": len(failed),
    }

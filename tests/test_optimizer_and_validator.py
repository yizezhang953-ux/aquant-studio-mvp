import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "optimization_module"))

from data_module import market_data as md  # noqa: E402
from helpers import wave, weekdays  # noqa: E402
from parameter_optimizer import run_optimization, split_windows  # noqa: E402
from strategy_validator import validate_strategy  # noqa: E402
from backtest_engine import Bar  # noqa: E402


def _db(tmp_path: Path, symbol: str = "600001.SH", n: int = 400) -> Path:
    db = tmp_path / "m.sqlite"
    md.init_db(db)
    market, exchange = md.market_for_symbol(symbol)
    with md.connect(db) as conn:
        bars = [md.Bar(symbol, "synthetic", market, exchange, "1d", d, c, c * 1.01, c * 0.99, c, 1e6, 1e8, 1.0, "synthetic")
                for d, c in zip(weekdays("2022-01-03", n), wave(n, amp=8, period=60))]
        md.insert_bars(conn, bars)
    return db


def _strategy(symbol: str, market: str) -> dict:
    strategy = json.loads((ROOT / "template_module" / "templates" / "double_ma_trend.json").read_text(encoding="utf-8"))
    strategy["universe"]["symbols"] = [symbol]
    strategy["market"] = market
    strategy["data"].update({"start_date": "2022-01-03", "end_date": "2023-12-31"})
    return strategy


def test_split_windows_holdout_and_walk_forward():
    bars = [Bar("x", "1d", d, 1, 1, 1, 1, 1, 1) for d in weekdays("2022-01-03", 100)]
    [hold] = split_windows(bars, "2022-01-01", "2030-01-01", {"method": "holdout", "train_ratio": 0.7})
    assert hold["train_end"] < hold["test_start"]
    folds = split_windows(bars, "2022-01-01", "2030-01-01", {"method": "walk_forward", "folds": 3})
    assert len(folds) == 3
    assert all(f["train_end"] < f["test_start"] for f in folds)
    assert folds[0]["test_end"] < folds[1]["test_start"]


def test_optimizer_ranks_on_train_and_reports_test(tmp_path):
    db = _db(tmp_path)
    base = tmp_path / "base.json"
    base.write_text(json.dumps(_strategy("600001.SH", "a_share")), encoding="utf-8")
    config = {
        "optimization_id": "t", "name": "t", "base_strategy": str(base), "db_path": str(db),
        "objective": {"primary_metric": "total_return", "direction": "max",
                      "tie_breakers": [{"metric": "sharpe", "direction": "max"}]},
        "validation": {"method": "holdout", "train_ratio": 0.6},
        "parameters": [
            {"name": "fast", "path": "entry.conditions.0.left.params.period", "values": [3, 5, 10]},
            {"name": "slow", "path": "entry.conditions.0.right.params.period", "values": [20, 40]},
        ],
    }
    cfg = tmp_path / "grid.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    summary = run_optimization(cfg, tmp_path / "out")
    assert summary["candidate_count"] == 6
    assert summary["validation"]["ranked_on"] == "train_total_return"
    rows = summary["results"]
    assert [r["train_total_return"] for r in rows] == sorted((r["train_total_return"] for r in rows), reverse=True)
    assert all("test_total_return" in r for r in rows)
    assert (tmp_path / "out" / "ranking.html").read_text(encoding="utf-8").count("验证期") >= 2
    assert "total_return" not in rows[0] and "full_total_return" in rows[0]  # full period never ranks

    config["validation"] = {"method": "walk_forward", "folds": 3}
    cfg.write_text(json.dumps(config), encoding="utf-8")
    walk = run_optimization(cfg, tmp_path / "out_wf")
    folds = walk["validation"]["fold_selection"]
    assert len(folds) == 3 and all(f["train_end"] < f["test_start"] for f in folds)
    assert walk["validation"]["out_of_sample_mean"] is not None


def test_validator_accepts_three_markets_and_rejects_mismatches(tmp_path):
    db = _db(tmp_path, "00700.HK")
    ok = validate_strategy(_strategy("00700.HK", "hk_connect"), db)
    assert ok.ok, ok.errors
    assert validate_strategy(_strategy("00700.HK", "hk_stock"), db).ok
    bad = validate_strategy(_strategy("00700.HK", "a_share"), db)
    assert not bad.ok and "cannot be traded in market a_share" in bad.errors[0]
    bad_symbol = validate_strategy(_strategy("700.HKG", "hk_connect"), db)
    assert not bad_symbol.ok
    unknown = _strategy("600519.SH", "us_stock")
    assert not validate_strategy(unknown).ok

"""Run the sector rotation backtest on a stored universe, for one factor and several look-back windows."""
from __future__ import annotations

import sys
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.services.legacy_paths import BACKTEST_MODULE
from app.services.sector_data_service import load_panel

if str(BACKTEST_MODULE) not in sys.path:
    sys.path.insert(0, str(BACKTEST_MODULE))

from rotation_engine import FACTOR_FIELDS, FACTORS, run_rotation  # noqa: E402

FIELD_NAMES = {"amount": "成交额", "float_mv": "流通市值", "buy_amount": "主动买入额", "sell_amount": "主动卖出额"}
AVERAGED = ("total_return", "annualized_return", "volatility", "sharpe", "max_drawdown", "calmar", "excess_annualized",
            "avg_turnover")


def factor_list() -> list[dict[str, Any]]:
    return [{"id": key, "name": name, "needs": list(FACTOR_FIELDS[key])} for key, name in FACTORS.items()]


def backtest(db: Session, *, universe: str, factor: str, windows: list[int], top_n: int, frequency: str,
             fee_rate: float, start: str | None, end: str | None) -> dict[str, Any]:
    days, codes, names, panel = load_panel(db, universe)
    if not days:
        raise ValueError("这个行业集合还没有数据，先同步或导入")
    lacking = [FIELD_NAMES[f] for f in FACTOR_FIELDS[factor] if np.isnan(panel[f]).all()]
    if lacking:
        raise ValueError(f"这份数据没有{'、'.join(lacking)}，算不了「{FACTORS[factor].split('（')[0]}」因子")
    if top_n > len(codes):
        raise ValueError(f"只有 {len(codes)} 个行业，选不出前 {top_n} 个")
    runs = [run_rotation(days, codes, panel, factor=factor, window=w, top_n=top_n, frequency=frequency,
                         fee_rate=fee_rate, start=start, end=end) for w in dict.fromkeys(windows)]
    first = runs[0]
    average = {}
    for key in AVERAGED:
        values = [r["metrics"][key] for r in runs if r["metrics"][key] is not None]
        average[key] = round(sum(values) / len(values), 6) if values else None
    return {
        "universe": universe, "factor": factor, "factor_name": FACTORS[factor], "top_n": top_n, "frequency": frequency,
        "fee_rate": fee_rate, "days": first["days"], "names": names,
        "benchmark_nav": first["benchmark_nav"], "benchmark_metrics": first["benchmark_metrics"],
        "average": average,
        "runs": [{"window": r["window"], "nav": r["nav"], "metrics": r["metrics"], "yearly": r["yearly"],
                  "rebalances": r["rebalances"]} for r in runs],
    }

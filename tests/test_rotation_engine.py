import numpy as np
import pytest

from data_module.sources import tushare
from rotation_engine import factor_values, performance, period_ends, rolling_mean, run_rotation

# Mon 2026-01-05 .. Fri 2026-01-23: three full trading weeks
DAYS = [f"2026-01-{d:02d}" for d in (5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23)]


def _panel(close: np.ndarray, **extra: np.ndarray) -> dict:
    return {"close": close, **extra}


def test_net_active_buy_is_net_share_over_turnover_share() -> None:
    buy = np.array([[60.0, 40.0]])
    sell = np.array([[30.0, 70.0]])
    amount = np.array([[100.0, 300.0]])
    out = factor_values("net_active_buy", _panel(np.ones((1, 2)), buy_amount=buy, sell_amount=sell, amount=amount), 1)
    # sector 0: (60/100 - 30/100) / (100/400) = 1.2 ; sector 1: (40/100 - 70/100) / (300/400) = -0.4
    assert out[0] == pytest.approx([1.2, -0.4])


def test_rolling_mean_needs_a_full_window() -> None:
    out = rolling_mean(np.array([[1.0], [np.nan], [3.0], [5.0], [7.0]]), 2)
    assert np.isnan(out[:3, 0]).all() and out[3:, 0] == pytest.approx([4.0, 6.0])


def test_period_ends_are_last_trading_days_and_skip_the_open_period() -> None:
    assert [DAYS[i] for i in period_ends(DAYS, "weekly")] == ["2026-01-09", "2026-01-16"]
    assert period_ends(DAYS, "monthly") == []


def test_signal_on_friday_trades_at_monday_close_and_weights_drift() -> None:
    close = np.ones((len(DAYS), 3)) * 100
    close[1:, 0] = 110  # sector 0 jumps in week 1: best 1-week momentum on Friday 01-09
    close[5:, 0] = 121  # ... and jumps again on Monday 01-12, the trade day: bought at the close, so not earned
    close[6:, 0] = 133.1  # Tuesday +10%: this is earned
    close[6:, 1] = 100  # sector 1 flat
    result = run_rotation(DAYS, ["A", "B", "C"], _panel(close), factor="momentum", window=3, top_n=1, frequency="weekly")
    first = result["rebalances"][0]
    assert (first["signal_date"], first["trade_date"]) == ("2026-01-09", "2026-01-12")
    assert [h["code"] for h in first["holdings"]] == ["A"] and first["turnover"] == 1.0
    nav = dict(zip(result["days"], result["nav"]))
    assert nav["2026-01-12"] == 1.0  # still cash on the trade day
    assert nav["2026-01-13"] == pytest.approx(1.1)
    # benchmark: equal weight of the three sectors, rebalanced daily
    bench = dict(zip(result["days"], result["benchmark_nav"]))
    assert bench["2026-01-06"] == pytest.approx(1 + 0.1 / 3)


def test_two_holdings_drift_between_rebalances_and_fees_are_charged_on_both_sides() -> None:
    close = np.ones((len(DAYS), 3)) * 100
    close[1:, 0], close[1:, 1] = 105, 102  # A and B lead on the first Friday
    close[6:, 0] = 105 * 1.2  # Tuesday: A +20%
    close[7:, 0] = 105 * 1.2 * 1.1  # Wednesday: A +10% again, now on a larger weight
    free = run_rotation(DAYS, ["A", "B", "C"], _panel(close), factor="momentum", window=3, top_n=2)
    nav = dict(zip(free["days"], free["nav"]))
    assert nav["2026-01-13"] == pytest.approx(1.1)  # half the portfolio +20%
    assert nav["2026-01-14"] == pytest.approx(1.1 * (1 + 0.1 * 0.6 / 1.1))  # A's weight drifted to 0.6/1.1
    paid = run_rotation(DAYS, ["A", "B", "C"], _panel(close), factor="momentum", window=3, top_n=2, fee_rate=0.001)
    assert dict(zip(paid["days"], paid["nav"]))["2026-01-12"] == pytest.approx(1 - 0.001)  # from cash: only the buy side trades


def test_unlisted_sectors_are_never_picked_and_do_not_drag_the_benchmark() -> None:
    close = np.ones((len(DAYS), 2)) * 100
    close[:8, 1] = np.nan  # sector B appears on 01-15
    close[1:, 0] = 101
    result = run_rotation(DAYS, ["A", "B"], _panel(close), factor="momentum", window=3, top_n=2)
    assert [h["code"] for h in result["rebalances"][0]["holdings"]] == ["A"]
    assert dict(zip(result["days"], result["benchmark_nav"]))["2026-01-06"] == pytest.approx(1.01)


def test_performance_uses_return_over_volatility_as_sharpe() -> None:
    nav = np.cumprod(np.r_[1.0, np.tile([1.01, 0.995], 126)])
    metrics = performance(nav)
    assert metrics["annualized_return"] == pytest.approx(nav[-1] - 1, abs=1e-6)  # exactly one year of days
    assert metrics["sharpe"] == pytest.approx(metrics["annualized_return"] / metrics["volatility"], abs=1e-3)
    assert metrics["max_drawdown"] == pytest.approx(-0.005, abs=1e-6)


# --------------------------------------------------------------------------- Tushare aggregation

def fake_tushare(tables: dict):
    calls = []

    def post(body: dict) -> dict:
        calls.append((body["api_name"], dict(body["params"])))
        rows = tables.get(body["api_name"], [])
        if callable(rows):
            rows = rows(body["params"])
        offset = body["params"].get("offset", 0)
        rows = rows[offset:offset + body["params"].get("limit", len(rows) or 1)]
        fields = list(rows[0]) if rows else []
        return {"code": 0, "msg": "", "data": {"fields": fields, "items": [[r[f] for f in fields] for r in rows]}}

    post.calls = calls
    return post


MEMBERS = [
    {"l1_code": "CI005021.CI", "l1_name": "银行", "l2_code": "CI005165.CI", "l2_name": "国有大型银行Ⅱ", "ts_code": "601398.SH",
     "in_date": "20100101", "out_date": None, "is_new": "Y"},
    {"l1_code": "CI005021.CI", "l1_name": "银行", "l2_code": "CI005166.CI", "l2_name": "全国性股份制银行Ⅱ", "ts_code": "600036.SH",
     "in_date": "20100101", "out_date": None, "is_new": "Y"},
    # a level-1 industry the report splits: the level-2 name is the sector
    {"l1_code": "CI005019.CI", "l1_name": "食品饮料", "l2_code": "CI005161.CI", "l2_name": "酒类", "ts_code": "600519.SH",
     "in_date": "20100101", "out_date": None, "is_new": "Y"},
    # left the sector before the test day
    {"l1_code": "CI005019.CI", "l1_name": "食品饮料", "l2_code": "CI005161.CI", "l2_name": "酒类", "ts_code": "000001.SZ",
     "in_date": "20100101", "out_date": "20200101", "is_new": "N"},
    # not one of the 40 sectors (综合)
    {"l1_code": "CI005029.CI", "l1_name": "综合", "l2_code": "CI005190.CI", "l2_name": "综合Ⅱ", "ts_code": "600000.SH",
     "in_date": "20100101", "out_date": None, "is_new": "Y"},
]


def test_tushare_stocks_are_summed_into_sectors_in_cny() -> None:
    flow = {k: 0.0 for k in ("buy_sm_amount", "sell_sm_amount", "buy_md_amount", "sell_md_amount", "buy_lg_amount",
                             "sell_lg_amount", "buy_elg_amount", "sell_elg_amount")}
    post = fake_tushare({
        "ci_index_member": lambda p: [m for m in MEMBERS if m["is_new"] == p["is_new"]],
        "daily": [{"ts_code": "601398.SH", "pct_chg": 10.0, "amount": 1000.0},
                  {"ts_code": "600036.SH", "pct_chg": -5.0, "amount": 2000.0},
                  {"ts_code": "600519.SH", "pct_chg": 1.0, "amount": 500.0},
                  {"ts_code": "000001.SZ", "pct_chg": 9.0, "amount": 500.0}],
        "daily_basic": [{"ts_code": "601398.SH", "circ_mv": 110.0}, {"ts_code": "600036.SH", "circ_mv": 95.0},
                        {"ts_code": "600519.SH", "circ_mv": 101.0}],
        "moneyflow": [{"ts_code": "601398.SH", **flow, "buy_sm_amount": 1.0, "buy_elg_amount": 2.0, "sell_md_amount": 1.5},
                      {"ts_code": "600036.SH", **flow, "buy_lg_amount": 4.0, "sell_lg_amount": 5.0}],
    })
    membership = tushare.fetch_membership("t", post)
    assert {m["sector"] for m in membership} == {"银行", "酒类"}
    rows = {r["name"]: r for r in tushare.fetch_sector_day("t", "2026-01-05", membership, post)}
    bank = rows["银行"]
    assert bank["stocks"] == 2 and bank["code"] == "CI005021.CI"
    assert bank["amount"] == pytest.approx(3_000_000)  # 千元 -> 元
    assert bank["float_mv"] == pytest.approx(2_050_000)  # 万元 -> 元
    assert bank["buy_amount"] == pytest.approx(70_000) and bank["sell_amount"] == pytest.approx(65_000)
    # yesterday both stocks were worth 100: (+10 - 5) / 200
    assert bank["ret"] == pytest.approx(0.025)
    assert rows["酒类"]["stocks"] == 1 and rows["酒类"]["code"] == "CI005161.CI"
    assert ("daily", {"trade_date": "20260105"}) in post.calls


def test_tushare_errors_carry_the_vendor_message() -> None:
    with pytest.raises(tushare.TushareError, match="权限"):
        tushare.query("t", "moneyflow", {}, post=lambda body: {"code": 2002, "msg": "抱歉，您没有访问该接口的权限"})

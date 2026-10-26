import sqlite3
import time

import pytest

from backtest_engine import Bar, CorporateAction, InstrumentInfo, MarketContext, load_bars, run_backtest
from helpers import gt, lt, make_bars, strategy, wave, weekdays
from market_rules_module import trading_calendar


def test_a_share_buys_whole_lots_and_pays_market_fees():
    closes = [100.0] * 5 + [105.0] * 5 + [90.0] * 5
    bars = make_bars("600519.SH", closes)
    report = run_backtest(strategy("600519.SH", "a_share", gt(102), lt(95), "2024-01-02", "2024-12-31", cash=100_000), bars)
    trade = report["trades"][0]
    assert trade["quantity"] % 100 == 0 and trade["quantity"] > 0
    # bought at the open after the signal (open = previous close = 105), sold at the next open after close < 95
    assert trade["entry_price"] == 105.0
    assert trade["entry_fee"] == pytest.approx(max(trade["quantity"] * 105 * 0.00025, 5) + round(trade["quantity"] * 105 * 0.00001, 2), abs=0.02)
    assert trade["exit_fee"] > trade["entry_fee"]  # stamp duty on the sell side
    assert report["metrics"]["currency"] == "CNY"


def test_order_smaller_than_one_lot_is_blocked_not_fractional():
    bars = make_bars("600519.SH", [1700.0] * 3 + [1720.0] * 5)
    report = run_backtest(strategy("600519.SH", "a_share", gt(1710), lt(1000), "2024-01-02", "2024-12-31", cash=100_000, size=0.3), bars)
    assert report["trades"] == [] and report["open_position"] is None
    assert report["metrics"]["blocked_orders"]["insufficient_cash_for_one_lot"] >= 1


def test_star_market_allows_odd_quantities_above_200():
    bars = make_bars("688981.SH", [50.0] * 3 + [60.0] * 5)
    report = run_backtest(strategy("688981.SH", "a_share", gt(55), lt(10), "2024-01-02", "2024-12-31", cash=15_000), bars)
    qty = report["open_position"]["quantity"]
    assert qty >= 200 and qty % 100 != 0


def test_limit_up_open_blocks_the_buy():
    closes = [10.0, 10.0, 10.5, 11.55, 11.6, 11.6]
    opens = [10.0, 10.0, 10.0, 11.55, 11.6, 11.6]  # day 3 opens at limit-up (10.5 * 1.1)
    bars = make_bars("600001.SH", closes, opens=opens)
    report = run_backtest(strategy("600001.SH", "a_share", gt(10.2), lt(5), "2024-01-02", "2024-12-31"), bars)
    assert report["metrics"]["blocked_orders"].get("limit_up") == 1
    assert report["open_position"]["entry_time"] == bars[4].trade_time  # filled the day after


def test_t_plus_one_blocks_same_day_exit_on_intraday_bars():
    times = ["2024-01-02 10:00:00", "2024-01-02 10:15:00", "2024-01-02 10:30:00", "2024-01-03 09:45:00"]
    closes = [10.0, 10.5, 9.0, 9.0]
    bars = [Bar("600001.SH", "15m", t, c, c * 1.001, c * 0.999, c, 100000, c * 100000) for t, c in zip(times, closes)]
    s = strategy("600001.SH", "a_share", gt(10.2), lt(9.5), "2024-01-02", "2024-01-03",
                 execution={"entry_price": "current_close", "exit_price": "current_close"})
    s["data"]["frequency"] = "15m"
    report = run_backtest(s, bars)
    trade = report["trades"][0]
    assert trade["entry_time"] == times[1]
    assert trade["exit_time"] == times[3]  # not on 2024-01-02
    assert report["metrics"]["blocked_orders"]["t_plus_one"] == 1  # 10:30 exit signal on the buy date
    assert report["metrics"]["periods_per_year"] == pytest.approx(242 * 240 / 15)


def test_hk_stock_uses_board_lot_from_instrument_and_warns_on_default():
    bars = make_bars("00168.HK", [40.0] * 3 + [45.0] * 5)
    s = strategy("00168.HK", "hk_stock", gt(42), lt(10), "2024-01-02", "2024-12-31", cash=500_000)
    with_lot = run_backtest(s, bars, MarketContext(instrument=InstrumentInfo("00168.HK", "青岛啤酒股份", lot_size=2000)))
    assert with_lot["open_position"]["quantity"] % 2000 == 0
    assert with_lot["currency"] == "HKD"
    default = run_backtest(s, bars)
    assert any("board lot" in w for w in default["warnings"])


def test_hk_connect_converts_currency_taxes_dividends_and_skips_mainland_holidays():
    if not trading_calendar.calendar_available():
        pytest.skip("exchange_calendars not installed")
    days = [d for d in weekdays("2024-09-23", 20) if d != "2024-10-01" and d != "2024-10-11"]  # HK holidays
    closes = [100.0, 100.0, 100.0, 100.0, 100.0, 106.0] + [107.0] * (len(days) - 6)
    bars = [Bar("00700.HK", "1d", d, c, c * 1.01, c * 0.99, c, 1e6, 1e8) for d, c in zip(days, closes)]
    assert bars[5].trade_time == "2024-09-30"  # signal day; next HK session 2024-10-02 is closed for 港股通
    ctx = MarketContext(
        instrument=InstrumentInfo("00700.HK", "腾讯控股", lot_size=100),
        fx_rates={"2024-09-01": 0.9},
        corporate_actions=[CorporateAction("2024-10-15", cash_dividend=2.0)],
    )
    s = strategy("00700.HK", "hk_connect", gt(105), lt(50), "2024-09-23", "2024-12-31", cash=200_000)
    report = run_backtest(s, bars, ctx)
    assert report["currency"] == "CNY" and report["quote_currency"] == "HKD"
    assert report["metrics"]["blocked_orders"]["suspended_or_market_closed"] == 4  # 10-02, 10-03, 10-04, 10-07
    position = report["open_position"]
    assert position["entry_time"] == "2024-10-08"
    qty = position["quantity"]
    assert qty % 100 == 0
    assert report["metrics"]["dividends_net"] == pytest.approx(qty * 2.0 * 0.9 * 0.8)
    assert report["metrics"]["dividend_tax"] == pytest.approx(qty * 2.0 * 0.9 * 0.2)
    # cost in CNY ≈ qty * price(HKD) * 0.9
    assert position["market_value"] == pytest.approx(qty * 107 * 0.9)


def test_a_share_dividend_tax_depends_on_holding_period():
    closes = [10.0, 10.0, 11.0] + [11.0] * 30 + [5.0, 5.0]
    bars = make_bars("600036.SH", closes)
    ex_date = bars[10].trade_time
    ctx = MarketContext(corporate_actions=[CorporateAction(ex_date, cash_dividend=0.5)])
    report = run_backtest(strategy("600036.SH", "a_share", gt(10.5), lt(6), "2024-01-02", "2024-12-31"), bars, ctx)
    trade = report["trades"][0]
    holding_days = (__import__("datetime").date.fromisoformat(trade["exit_time"]) -
                    __import__("datetime").date.fromisoformat(trade["entry_time"])).days
    assert 30 < holding_days <= 365
    assert trade["dividend_tax"] == pytest.approx(trade["quantity"] * 0.5 * 0.10)


def test_signals_use_adjusted_prices_and_dividends_are_derived_from_adj_factor():
    raw = [20.0] * 10 + [19.0] * 10  # ex-dividend of 1.0 on bar 10
    factors = [0.95] * 10 + [1.0] * 10
    bars = make_bars("601398.SH", raw, factors=factors)
    s = strategy("601398.SH", "a_share", gt(0), lt(0), "2024-01-02", "2024-12-31", adjustment="forward")
    report = run_backtest(s, bars)
    assert any("derived from adj_factor" in w for w in report["warnings"])
    assert report["metrics"]["dividends_net"] > 0
    assert report["metrics"]["benchmark_return"] == pytest.approx(0.0, abs=1e-9)  # total return flat


def test_max_drawdown_stop_liquidates_and_halts():
    closes = [100.0, 101.0] + [100.0 - i * 2 for i in range(20)]
    bars = make_bars("600001.SH", closes)
    risk = {"stop_loss_pct": None, "take_profit_pct": None, "max_drawdown_pct": 0.1, "max_holding_bars": None}
    report = run_backtest(strategy("600001.SH", "a_share", gt(0), lt(-1), "2024-01-02", "2024-12-31", risk=risk), bars)
    assert len(report["trades"]) == 1
    assert report["trades"][0]["exit_reason"] == "max_drawdown_stop"
    assert report["open_position"] is None


def test_macd_and_bollinger_are_supported():
    bars = make_bars("600001.SH", wave(300))
    entry = {"logic": "all", "conditions": [{"left": {"type": "indicator", "name": "MACD", "params": {"output": "macd"}},
                                             "operator": "cross_above",
                                             "right": {"type": "indicator", "name": "MACD", "params": {"output": "signal"}}}]}
    exit_ = {"logic": "any", "conditions": [{"left": {"type": "price", "field": "close"}, "operator": "gt",
                                             "right": {"type": "indicator", "name": "BOLL", "params": {"period": 20, "std": 2, "output": "upper"}}},
                                            {"left": {"type": "indicator", "name": "MACD", "params": {"output": "hist"}},
                                             "operator": "lt", "right": {"type": "constant", "value": 0}}]}
    report = run_backtest(strategy("600001.SH", "a_share", entry, exit_, "2024-01-02", "2025-12-31"), bars)
    assert report["metrics"]["trade_count"] > 0
    assert report["metrics"]["annualized_return"] is not None


def test_engine_scales_linearly():
    bars = make_bars("600001.SH", wave(20_000, period=97))
    entry = {"logic": "all", "conditions": [{"left": {"type": "indicator", "name": "MA", "params": {"period": 5}},
                                             "operator": "cross_above", "right": {"type": "indicator", "name": "MA", "params": {"period": 60}}}]}
    exit_ = {"logic": "any", "conditions": [{"left": {"type": "indicator", "name": "MA", "params": {"period": 5}},
                                             "operator": "cross_below", "right": {"type": "indicator", "name": "MA", "params": {"period": 60}}}]}
    started = time.perf_counter()
    report = run_backtest(strategy("600001.SH", "a_share", entry, exit_, "2024-01-02", "2200-01-01"), bars)
    assert time.perf_counter() - started < 10
    assert report["metrics"]["trade_count"] > 50


def test_load_bars_includes_warmup_history(tmp_path):
    db = tmp_path / "m.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE bars (symbol, frequency, trade_time, open, high, low, close, volume, amount, adj_factor)")
        for day, close in zip(weekdays("2024-01-02", 100), wave(100)):
            conn.execute("INSERT INTO bars VALUES (?, '1d', ?, ?, ?, ?, ?, 1, 1, 1)", ("600001.SH", day, close, close, close, close))
    s = strategy("600001.SH", "a_share",
                 {"logic": "all", "conditions": [{"left": {"type": "indicator", "name": "MA", "params": {"period": 20}},
                                                  "operator": "gt", "right": {"type": "constant", "value": 0}}]},
                 lt(0), "2024-03-01", "2024-12-31")
    bars = load_bars(db, s)
    assert bars[0].trade_time < "2024-03-01" and len([b for b in bars if b.trade_time < "2024-03-01"]) == 21
    report = run_backtest(s, bars)
    assert report["equity_curve"][0]["trade_time"] >= "2024-03-01"
    assert report["open_position"]["entry_time"] == report["equity_curve"][1]["trade_time"]  # MA ready on day 1


def test_bars_without_volume_still_trade():
    bars = make_bars("600001.SH", [10.0, 10.0, 11.0, 11.0, 11.0], volume=0)
    report = run_backtest(strategy("600001.SH", "a_share", gt(10.5), lt(5), "2024-01-02", "2024-12-31"), bars)
    assert report["open_position"] is not None
    assert any("no volume" in w for w in report["warnings"])


def test_zero_fx_rates_are_ignored():
    bars = [Bar("00700.HK", "1d", d, 100, 101, 99, 100 + i, 1e6, 1e8) for i, d in enumerate(weekdays("2024-03-01", 10))]
    ctx = MarketContext(instrument=InstrumentInfo("00700.HK", lot_size=100), fx_rates={"2024-03-01": 0.0})
    report = run_backtest(strategy("00700.HK", "hk_connect", gt(102), lt(1), "2024-03-01", "2024-12-31"), bars, ctx)
    assert report["open_position"] is not None
    assert any("default rate" in w for w in report["warnings"])


def test_highest_and_lowest_look_at_previous_bars_only():
    from indicators import prior_extreme

    values = [3, 1, 4, 1, 5, 9, 2, 6]
    assert prior_extreme(values, 3, highest=True) == [None, None, None, 4, 4, 5, 9, 9]
    assert prior_extreme(values, 3, highest=False) == [None, None, None, 1, 1, 1, 1, 2]


@pytest.mark.parametrize("name", ["connors_rsi2", "boll_reversion", "myquant_macd_zero", "turtle_donchian"])
def test_open_source_templates_validate_and_trade(name):
    import json
    import math
    from pathlib import Path

    from strategy_validator import validate_strategy

    template = json.loads((Path(__file__).resolve().parents[1] / "template_module" / "templates" / f"{name}.json").read_text("utf-8"))
    assert validate_strategy(template).ok
    # uptrend with regular pullbacks; the MACD template only buys crosses above zero, so give it a steeper trend
    drift, swing = (1.002, 0.02) if name == "myquant_macd_zero" else (1.0006, 0.06)
    closes = [round(100 * drift ** i * (1 + swing * math.sin(2 * math.pi * i / 30)), 2) for i in range(900)]
    symbol = template["universe"]["symbols"][0]
    bars = make_bars(symbol, closes, start="2020-01-02")
    template["data"].update(start_date=bars[0].trade_time, end_date=bars[-1].trade_time, adjustment="none")
    report = run_backtest(template, bars)
    assert len(report["trades"]) >= 3, name

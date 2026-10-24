import pytest

from market_rules_module import market_rules as mr
from market_rules_module import trading_calendar
from datetime import date


RULES = mr.load_rules()


def test_symbol_normalisation_and_market_resolution():
    assert mr.normalize_symbol("700.hk") == "00700.HK"
    assert mr.normalize_symbol("sh600519") == "600519.SH"
    assert mr.normalize_symbol("000001") == "000001.SZ"
    assert mr.get_market_rule(RULES, "600519.SH")[0] == "a_share"
    assert mr.get_market_rule(RULES, "00700.HK")[0] == "hk_stock"
    assert mr.get_market_rule(RULES, "00700.HK", "hk_connect")[0] == "hk_connect"
    assert mr.get_market_rule(RULES, "00700.HK", "港股通")[0] == "hk_connect"
    assert mr.get_market_rule(RULES, "600519.SH", "hk_connect") == (None, None)
    _, connect = mr.get_market_rule(RULES, "00700.HK", "hk_connect")
    assert connect["currency"] == "CNY" and connect["quote_currency"] == "HKD"
    assert connect["board_lots"]["00005.HK"] == 400  # inherited from hk_stock


def test_lot_rules_by_board_and_market():
    _, a = mr.get_market_rule(RULES, "600519.SH")
    assert mr.round_buy_quantity(mr.lot_rule(a, "600519.SH"), 250.7) == 200
    star = mr.lot_rule(a, "688981.SH")
    assert (star.buy_min_qty, star.buy_step) == (200, 1)
    assert mr.round_buy_quantity(star, 250.7) == 250
    assert mr.round_buy_quantity(star, 150) == 0
    _, hk = mr.get_market_rule(RULES, "00005.HK")
    assert mr.round_buy_quantity(mr.lot_rule(hk, "00005.HK"), 1000) == 800
    feed_lot = mr.lot_rule(hk, "00168.HK", instrument_lot_size=2000)
    assert (feed_lot.lot_size, feed_lot.lot_source) == (2000, "instrument")
    assert mr.lot_rule(hk, "01299.HK").lot_source == "default"


def test_price_limits_by_board_and_date():
    _, a = mr.get_market_rule(RULES, "600519.SH")
    assert mr.price_limit_pct(a, "600519.SH") == 0.10
    assert mr.price_limit_pct(a, "600123.SH", name="*ST 某某") == 0.05
    assert mr.price_limit_pct(a, "300750.SZ", trade_date="2020-08-01") == 0.10
    assert mr.price_limit_pct(a, "300750.SZ", trade_date="2024-01-02") == 0.20
    assert mr.price_limit_pct(a, "688981.SH") == 0.20
    assert mr.price_limit_pct(a, "430047.BJ") == 0.30
    _, hk = mr.get_market_rule(RULES, "00700.HK")
    assert mr.price_limit_pct(hk, "00700.HK") is None
    assert mr.limit_prices(10.0, 0.10) == (9.0, 11.0)
    assert mr.limit_prices(12.34, 0.10) == (11.11, 13.57)


def test_a_share_fees_follow_stamp_duty_cut():
    before = mr.calculate_fee_breakdown(RULES, "600519.SH", "sell", 100_000, trade_date="2023-08-01")
    after = mr.calculate_fee_breakdown(RULES, "600519.SH", "sell", 100_000, trade_date="2024-01-02")
    assert before.components == {"commission": 25.0, "transfer_fee": 1.0, "stamp_duty": 100.0}
    assert after.total_fee == pytest.approx(76.0)
    small_buy = mr.calculate_fee_breakdown(RULES, "600519.SH", "buy", 10_000, trade_date="2024-01-02")
    assert small_buy.components["commission"] == 5.0  # minimum commission
    assert "stamp_duty" not in small_buy.components


def test_hk_and_connect_fees():
    hk = mr.calculate_fee_breakdown(RULES, "00700.HK", "buy", 100_000, trade_date="2024-01-02")
    assert hk.components["stamp_duty"] == 100.0
    assert hk.total_fee == pytest.approx(30 + 2.7 + 0.15 + 5.65 + 2.0 + 100)
    hk_2022 = mr.calculate_fee_breakdown(RULES, "00700.HK", "sell", 100_000, trade_date="2022-06-01")
    assert hk_2022.components["stamp_duty"] == 130.0
    assert "transfer_deed_stamp_duty" not in hk_2022.components
    connect = mr.calculate_fee_breakdown(RULES, "00700.HK", "buy", 100_000, market="hk_connect", trade_date="2024-01-02")
    assert connect.market == "hk_connect"
    assert connect.total_fee == pytest.approx(25 + 2.7 + 0.15 + 5.65 + 2.0 + 100)


def test_dividend_tax_rules():
    _, a = mr.get_market_rule(RULES, "600519.SH")
    assert mr.dividend_tax_rate(a, "600519.SH", 10) == 0.20
    assert mr.dividend_tax_rate(a, "600519.SH", 100) == 0.10
    assert mr.dividend_tax_rate(a, "600519.SH", 400) == 0.0
    _, connect = mr.get_market_rule(RULES, "00700.HK", "hk_connect")
    assert mr.dividend_tax_rate(connect, "00700.HK") == 0.20


def test_order_validation_for_each_market():
    base = {"side": "buy", "order_type": "limit", "quantity": 150}
    a = mr.validate_market_order(RULES, {**base, "symbol": "600519.SH"}, {})
    assert not a.accepted and "multiple of 100" in a.reasons[0]
    hk = mr.validate_market_order(RULES, {**base, "symbol": "00005.HK", "quantity": 400}, {})
    assert hk.accepted, hk.reasons
    connect = mr.validate_market_order(
        RULES, {**base, "symbol": "00700.HK", "market": "hk_connect", "quantity": 100, "connect_eligible": False}, {}
    )
    assert not connect.accepted and "Stock Connect" in connect.reasons[0]
    sell = mr.validate_market_order(
        RULES, {"symbol": "600519.SH", "side": "sell", "order_type": "limit", "quantity": 100},
        {"positions": {"600519.SH": 100}, "available_positions": {"600519.SH": 0}},
    )
    assert not sell.accepted and "T+1" in sell.reasons[0]
    limited = mr.validate_market_order(
        RULES, {**base, "symbol": "600519.SH", "quantity": 100, "estimated_price": 11.5, "market_snapshot": {"prev_close": 10.0}}, {}
    )
    assert any("price limit" in reason for reason in limited.reasons)


def test_connect_calendar_requires_both_markets_open():
    days, source = trading_calendar.trading_days("hk_connect", date(2024, 9, 30), date(2024, 10, 8))
    if source != "exchange_calendars":
        pytest.skip("exchange_calendars not installed")
    assert date(2024, 9, 30) in days
    assert date(2024, 10, 2) not in days  # HK open, mainland National Day holiday
    hk_days, _ = trading_calendar.trading_days("hk_stock", date(2024, 9, 30), date(2024, 10, 8))
    assert date(2024, 10, 2) in hk_days
    a_days, _ = trading_calendar.trading_days("a_share", date(2025, 1, 27), date(2025, 2, 5))
    assert date(2025, 1, 29) not in a_days  # Spring Festival 2025 (not in the old 2024-only list)

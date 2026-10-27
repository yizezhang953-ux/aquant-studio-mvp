"""Parsers for the free data sources, using response shapes observed from the live APIs."""
import sqlite3

from data_module import market_data as md
from data_module.sources import fx, tencent


A_RAW = {"code": 0, "data": {"sh600519": {"day": [
    ["2024-01-02", "1715.000", "1685.010", "1718.190", "1678.100", "32156.000"],
    ["2024-01-03", "1681.110", "1694.000", "1695.220", "1676.330", "20227.000"],
]}}}
A_QFQ = {"code": 0, "data": {"sh600519": {"qfqday": [
    ["2024-01-02", "1580.661", "1550.671", "1583.851", "1543.761", "32156.000"],
    ["2024-01-03", "1546.771", "1559.661", "1560.881", "1541.991", "20227.000"],
]}}}
HK_RAW = {"code": 0, "data": {"hk00700": {"day": [
    ["2024-01-02", "300.000", "296.600", "305.000", "294.400", "23354069.000", {}],
]}}}
HK_QFQ = {"code": 0, "data": {"hk00700": {"qfqday": [
    ["2024-01-02", "286.800", "283.400", "291.800", "281.200", "23354069.000", {}, "0.250", "696238.386"],
]}}}


def fake_fetch(url, params):
    param = params["param"]
    if param.startswith("sh600519"):
        return A_QFQ if param.endswith("qfq") else A_RAW
    if "hkfqkline" in url:
        return HK_QFQ
    return HK_RAW


def test_tencent_a_share_bars_are_raw_with_adj_factor_and_shares_volume():
    bars = tencent.fetch_daily("600519.SH", "2024-01-01", "2024-01-03", fetch=fake_fetch)
    assert [b["trade_time"] for b in bars] == ["2024-01-02", "2024-01-03"]
    first = bars[0]
    assert first["close"] == 1685.01 and first["open"] == 1715.0
    assert first["volume"] == 3_215_600  # 32156 lots of 100 shares
    assert [b["adj_factor"] for b in bars] == [1.0, 1.0]  # constant gap (raw - qfq) = no ex-date in between


def test_tencent_subtractive_qfq_gap_change_becomes_a_dividend():
    raw = {"2024-06-18": {"open": 10, "high": 10, "low": 10, "close": 10.0, "volume": 1, "amount": 0},
           "2024-06-19": {"open": 9.5, "high": 9.5, "low": 9.5, "close": 9.6, "volume": 1, "amount": 0},
           "2024-06-20": {"open": 9.6, "high": 9.6, "low": 9.6, "close": 9.7, "volume": 1, "amount": 0}}
    qfq = {"2024-06-18": {**raw["2024-06-18"], "close": 9.5}, "2024-06-19": {**raw["2024-06-19"], "close": 9.6},
           "2024-06-20": {**raw["2024-06-20"], "close": 9.7}}
    result = tencent.merge_raw_and_adjusted("600036.SH", raw, qfq)
    assert result["actions"] == [{"ex_date": "2024-06-19", "cash_dividend": 0.5, "bonus_ratio": 0.0}]
    factors = [b["adj_factor"] for b in result["bars"]]
    assert factors == [0.95, 1.0, 1.0]


def test_tencent_bonus_shares_are_detected():
    raw = {"2024-05-30": {"open": 20, "high": 20, "low": 20, "close": 20.0, "volume": 1, "amount": 0},
           "2024-05-31": {"open": 10, "high": 10, "low": 10, "close": 10.2, "volume": 1, "amount": 0}}
    qfq = {"2024-05-30": {**raw["2024-05-30"], "close": 10.0}, "2024-05-31": {**raw["2024-05-31"], "close": 10.2}}
    result = tencent.merge_raw_and_adjusted("300001.SZ", raw, qfq)
    assert result["actions"][0]["bonus_ratio"] == 1.0  # 10转10


def test_tencent_hk_bars_use_turnover_and_kline_endpoint():
    bars = tencent.fetch_daily("00700.HK", "2024-01-01", "2024-01-02", fetch=fake_fetch)
    assert bars[0]["close"] == 296.6 and bars[0]["volume"] == 23_354_069
    assert abs(bars[0]["amount"] - 6_962_383_860) < 1


def test_tencent_index_closes_use_the_index_code():
    calls = []

    def fetch(url, params):
        calls.append((url, params["param"]))
        code = params["param"].split(",")[0]
        return {"data": {code: {"day": [["2024-01-02", "1", "16788.5", "1", "1", "0"], ["2024-01-03", "1", "16645.9", "1", "1", "0"]]}}}

    assert tencent.fetch_index_daily("hkHSI", "2024-01-01", "2024-01-05", fetch) == {"2024-01-02": 16788.5, "2024-01-03": 16645.9}
    assert calls[0] == (tencent.KLINE_HK_RAW, "hkHSI,day,2024-01-01,2024-01-05,400")
    tencent.fetch_index_daily("sh000300", "2023-12-01", "2024-01-05", fetch)
    assert [c[0] for c in calls[1:]] == [tencent.KLINE_A, tencent.KLINE_A]  # one request per calendar year


def test_fx_parser():
    payload = {"base": "HKD", "rates": {"2024-01-02": {"CNY": 0.9125}, "2024-01-03": {"CNY": 0.9131}}}
    rates = fx.fetch_rates("HKD", "CNY", "2024-01-01", "2024-01-03", fetch=lambda url, params: payload)
    assert rates == {"2024-01-02": 0.9125, "2024-01-03": 0.9131}


def test_v1_database_is_migrated_to_multi_market(tmp_path):
    db = tmp_path / "v1.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE instruments (symbol TEXT PRIMARY KEY, name TEXT NOT NULL,
              market TEXT NOT NULL CHECK (market = 'a_share'), exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ')),
              asset_type TEXT NOT NULL DEFAULT 'stock', listed_date TEXT, status TEXT NOT NULL DEFAULT 'active',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE bars (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, frequency TEXT NOT NULL,
              trade_time TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
              volume REAL NOT NULL, amount REAL NOT NULL, adj_factor REAL NOT NULL DEFAULT 1.0, source TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE (symbol, frequency, trade_time),
              FOREIGN KEY (symbol) REFERENCES instruments(symbol));
            CREATE TABLE data_loads (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, symbol TEXT NOT NULL,
              frequency TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT,
              row_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, error_message TEXT,
              FOREIGN KEY (symbol) REFERENCES instruments(symbol));
            INSERT INTO instruments(symbol, name, market, exchange) VALUES ('600519.SH', '贵州茅台', 'a_share', 'SH');
            INSERT INTO bars(symbol, frequency, trade_time, open, high, low, close, volume, amount, source)
            VALUES ('600519.SH', '1d', '2024-01-02', 1, 1, 1, 1, 1, 1, 'x');
            """
        )
    md.init_db(db)
    with md.connect(db) as conn:
        md.upsert_instrument(conn, "00700.HK", "腾讯控股", lot_size=100)
        bars = [md.Bar(name="腾讯控股", market="hk_stock", exchange="HK", **row)
                for row in tencent.fetch_daily("00700.HK", "2024-01-01", "2024-01-02", fetch=fake_fetch)]
        md.insert_bars(conn, bars)
        md.upsert_fx_rates(conn, "HKDCNY", {"2024-01-02": 0.91}, "test")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        row = conn.execute("SELECT market, currency, lot_size FROM instruments WHERE symbol = '00700.HK'").fetchone()
        assert tuple(row) == ("hk_stock", "HKD", 100)
    health = md.data_health(db)
    assert health["bar_count"] == 2 and health["fx_rates"][0]["pair"] == "HKDCNY"


def test_factors_stay_continuous_across_sync_windows(tmp_path):
    from data_module.adjust import factors_from_actions

    days = ["2024-01-02", "2024-01-03", "2024-06-03", "2024-06-04"]
    closes = [10.0, 10.0, 10.0, 9.5]
    factors = factors_from_actions(days, closes, [{"ex_date": "2024-06-04", "cash_dividend": 0.5}])
    assert factors == [0.95, 0.95, 0.95, 1.0]
    # a dividend dated on a non-trading day applies to the next session
    assert factors_from_actions(days, closes, [{"ex_date": "2024-06-01", "cash_dividend": 0.5}])[1] == 0.95

    db = tmp_path / "w.sqlite"
    md.init_db(db)
    with md.connect(db) as conn:
        bars = [md.Bar("600036.SH", "x", "a_share", "SH", "1d", d, c, c, c, c, 1, 1, 1.0, "t") for d, c in zip(days, closes)]
        md.insert_bars(conn, bars)
        md.upsert_corporate_actions(conn, "600036.SH", [{"ex_date": "2024-01-03", "cash_dividend": 0.2}], "tencent_derived", "2024-01-01", "2024-01-31")
        md.upsert_corporate_actions(conn, "600036.SH", [{"ex_date": "2024-06-04", "cash_dividend": 0.5}], "tencent_derived", "2024-06-01", "2024-06-30")
        assert len(md.effective_actions(conn, "600036.SH")) == 2  # the second window kept the first one's dividend
        md.rebuild_adj_factors(conn, "600036.SH")
        stored = [r[0] for r in conn.execute("SELECT adj_factor FROM bars ORDER BY trade_time")]
    assert stored[-1] == 1.0 and stored[2] == 0.95 and stored[0] < stored[1]


def test_tencent_live_quotes_parse_a_share_hk_and_suspended():
    from data_module.sources.tencent import fetch_quotes

    pad = lambda n: "~".join(["0"] * n)  # noqa: E731
    a = f"1~贵州茅台~600519~1500.50~1490.00~1492.00~23456~1~2~{pad(21)}~20261027143001~10.50~0.70~1505.00~1488.00~x~y~350000~"
    hk = f"100~腾讯控股~00700~420.200~415.000~416.000~12345678.0~{pad(23)}~2026/10/27 16:08:12~5.2~1.25~423.0~414.0~x~y~5180000000~"
    halted = f"1~平安银行~000001~0.00~11.00~0.00~0~{pad(40)}"
    text = f'v_sh600519="{a}";\nv_hk00700="{hk}";\nv_sz000001="{halted}";'.encode("gbk")
    urls = []
    quotes = fetch_quotes(["600519.SH", "00700.HK", "000001.SZ"], lambda url: urls.append(url) or text)
    assert urls == ["https://qt.gtimg.cn/q=sh600519,hk00700,sz000001"]
    moutai = quotes["600519.SH"]
    assert moutai["name"] == "贵州茅台" and moutai["price"] == 1500.5 and moutai["volume"] == 2_345_600
    assert moutai["amount"] == 3_500_000_000 and moutai["time"] == "2026-10-27 14:30:01" and moutai["traded"]
    assert quotes["00700.HK"]["time"] == "2026-10-27 16:08:12" and quotes["00700.HK"]["volume"] == 12_345_678
    assert quotes["000001.SZ"]["price"] == 11.0 and not quotes["000001.SZ"]["traded"]

import time

from app.db.session import SessionLocal
from app.services import quote_service
from app.services.auth_service import set_admin
from app.services.json_utils import read_json
from app.services.legacy_paths import TEMPLATE_MODULE
from app.services.market_sync_service import start_dates
from app.services.signal_service import with_live_bar
from backtest_engine import Bar
from test_app import _oscillating, a_symbol, register


def _admin(client):
    headers, _ = register(client, "bulk")
    from app.models import User
    with SessionLocal() as db:
        set_admin(db, db.query(User).order_by(User.id.desc()).first().email)
    return headers


def _wait(client, headers, timeout=20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get("/api/v1/market/sync-batch", headers=headers).json()["job"]
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("batch sync did not finish")


def test_batch_sync_fetches_many_stocks_and_only_tops_up_known_ones(client) -> None:
    headers = _admin(client)
    codes = [a_symbol("SH")[:6], "sz" + a_symbol("SZ")[:6], a_symbol("HK")]  # as people paste them
    bad = client.post("/api/v1/market/sync-batch", headers=headers, json={
        "symbols": ["600519", "ABC"], "start_date": "2026-01-01", "provider_id": "demo"})
    assert bad.status_code == 400 and "ABC" in bad.json()["detail"]

    started = client.post("/api/v1/market/sync-batch", headers=headers, json={
        "symbols": codes, "start_date": "2026-01-01", "end_date": "2026-10-23", "provider_id": "demo"})
    assert started.status_code == 200, started.text
    job = _wait(client, headers)
    assert job["status"] == "done" and job["ok"] == 3 and job["failed"] == []
    symbols = job["symbols"]
    assert symbols[0].endswith(".SH") and symbols[1].endswith(".SZ") and symbols[2].endswith(".HK")
    listed = {i["symbol"]: i for i in client.get("/api/v1/market/instruments").json()["instruments"]}
    assert all(s in listed and listed[s]["last_trade_time"][:10] == "2026-10-23" for s in symbols)

    with SessionLocal() as db:  # known stocks restart a week before their last bar; new ones at the given date
        starts = start_dates(db, symbols + ["600000.SH"], "2020-01-01")
    assert starts[symbols[0]] == "2026-10-16" and starts["600000.SH"] == "2020-01-01"

    user, _ = register(client, "bulk-viewer")
    assert client.post("/api/v1/market/sync-batch", headers=user, json={
        "symbols": codes, "start_date": "2026-01-01", "provider_id": "demo"}).status_code == 403


def test_live_quotes_and_intraday_signals(client, monkeypatch) -> None:
    headers = _admin(client)
    symbol = a_symbol("SZ")
    days = _oscillating(client, headers, symbol)
    quote = {"symbol": symbol, "name": "实时", "price": 99.0, "prev_close": 30.0, "open": 30.0, "high": 99.0, "low": 30.0,
             "volume": 1000.0, "amount": 99000.0, "change": 69.0, "change_pct": 2.3, "time": "2025-01-02 10:31:00",
             "traded": True}
    calls = []
    monkeypatch.setattr(quote_service.tencent, "fetch_quotes",
                        lambda symbols, fetch_bytes=None: calls.append(list(symbols)) or {symbol: quote})
    quote_service._cache.clear()

    first = client.get(f"/api/v1/market/quotes?symbols={symbol[:6]}").json()["quotes"]
    again = client.get(f"/api/v1/market/quotes?symbols={symbol}").json()["quotes"]
    assert first[0]["price"] == 99.0 and again == first and len(calls) == 1  # second read comes from the cache

    strategy = read_json(TEMPLATE_MODULE / "templates" / "rsi_reversal.json")
    body = {"strategies": [{"strategy_id": "s", "name": "RSI", "strategy": strategy}], "symbols": [symbol]}
    closed = client.post("/api/v1/signals/scan", headers=headers, json=body).json()["rows"][0]
    live = client.post("/api/v1/signals/scan", headers=headers, json={**body, "live": True}).json()["rows"][0]
    assert closed["date"][:10] == days[-1] and not closed["live"]
    assert live["live"] and live["date"] == "2025-01-02" and live["close"] == 99.0
    assert live["signal"] == "sell"  # RSI jumps above 70 on a +230% "close"


def test_live_bar_replaces_today_or_is_appended() -> None:
    bars = [Bar("A", "1d", "2026-10-26", 10, 11, 9, 10, 100, 1000, 0.5), Bar("A", "1d", "2026-10-27", 10, 11, 9, 10.5, 50, 500, 1.0)]
    quote = {"price": 11.0, "open": 10.2, "high": 11.2, "low": 10.0, "volume": 80, "amount": 880, "time": "2026-10-27 14:00:00",
             "traded": True}
    same_day, used = with_live_bar(bars, quote)
    assert used and len(same_day) == 2 and same_day[-1].close == 11.0 and same_day[-1].adj_factor == 1.0
    next_day, used = with_live_bar(bars, {**quote, "time": "2026-10-28 09:45:00"})
    assert used and len(next_day) == 3 and next_day[-1].trade_time == "2026-10-28"
    assert with_live_bar(bars, {**quote, "traded": False}) == (bars, False)  # suspended / before the open

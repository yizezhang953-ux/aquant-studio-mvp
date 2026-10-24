import gzip
import json
import random
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.core.config import Settings
from app.db.session import SessionLocal, connect_args_for, normalize_database_url
from app.models import User, UserSession
from app.services import market_data_source_service as sources
from app.services.auth_service import hash_password, verify_password
from app.services.database_backup_service import create_database_backup, read_backup_metadata, restore_database_backup
from app.services.json_utils import read_json
from app.services.legacy_paths import TEMPLATE_MODULE

PASSWORD = "strong-password-123"


def register(client, prefix: str = "user") -> tuple[dict, dict]:
    email = f"{prefix}-{uuid4().hex[:8]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": prefix})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, response.json()


def a_symbol(exchange: str = "SH") -> str:
    if exchange == "HK":
        return f"{random.randint(10000, 99999):05d}.HK"
    first = {"SH": "60", "SZ": "00", "BJ": "83"}[exchange]
    return f"{first}{random.randint(1000, 9999)}.{exchange}"


def bar(symbol: str, day: str, close: float, **extra) -> dict:
    return {"symbol": symbol, "frequency": "1d", "trade_time": day, "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1000, "amount": close * 1000, **extra}


# --------------------------------------------------------------------------- basics


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_status_blocks_live_trading(client) -> None:
    response = client.get("/api/v1/security/status")
    assert response.status_code == 200
    assert response.json()["live_trading_status"] == "blocked_for_live_trading"


def test_templates_cover_all_three_markets(client) -> None:
    response = client.get("/api/v1/templates")
    assert response.status_code == 200
    markets = {item["market"] for item in response.json()["templates"]}
    assert {"a_share", "hk_stock", "hk_connect"} <= markets


def test_strategy_validation_uses_web_database_coverage(client) -> None:
    strategy = read_json(TEMPLATE_MODULE / "templates" / "price_breakout.json")
    response = client.post("/api/v1/strategies/validate", json={"strategy": strategy})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    hk = read_json(TEMPLATE_MODULE / "templates" / "hk_connect_ma_trend.json")
    hk["universe"]["symbols"] = ["09999.HK"]
    missing = client.post("/api/v1/strategies/validate", json={"strategy": hk}).json()
    assert missing["ok"] is False and "no market data" in missing["errors"][0]


def test_settings_parse_comma_separated_lists_and_admin_defaults() -> None:
    settings = Settings(allowed_origins="https://app.example.com, https://api.example.com")
    assert settings.allowed_origins == ["https://app.example.com", "https://api.example.com"]
    assert Settings(app_env="local").first_user_admin_enabled is True
    assert Settings(app_env="production").first_user_admin_enabled is False


def test_database_url_supports_postgresql_driver_normalization() -> None:
    assert normalize_database_url("postgres://user:pass@localhost:5432/aquant") == "postgresql+psycopg://user:pass@localhost:5432/aquant"
    assert normalize_database_url("postgresql://user:pass@localhost:5432/aquant") == "postgresql+psycopg://user:pass@localhost:5432/aquant"
    assert connect_args_for("sqlite:///./aquant_web_app.db") == {"check_same_thread": False}
    assert connect_args_for("postgresql+psycopg://user:pass@localhost:5432/aquant") == {}


# --------------------------------------------------------------------------- auth and permissions


def test_database_init_requires_admin(client, admin_headers) -> None:
    assert client.post("/api/v1/database/init").status_code == 401
    user_headers, _ = register(client, "plain")
    assert client.post("/api/v1/database/init", headers=user_headers).status_code == 403
    response = client.post("/api/v1/database/init", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["tables"]["strategy_templates"] >= 7
    assert payload["tables"]["market_bars"] >= 1
    status = client.get("/api/v1/database/status").json()
    assert status["dialect"] in {"sqlite", "postgresql"} and "market_fx_rates" in status["tables"]


def test_tokens_are_stored_hashed_and_logins_are_throttled(client) -> None:
    headers, payload = register(client, "token")
    token = headers["Authorization"].split()[1]
    with SessionLocal() as db:
        stored = db.scalars(sa.select(UserSession.token)).all()
    assert token not in stored
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    email = payload["user"]["email"]
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 429


def test_legacy_password_hash_is_upgraded_on_login(client) -> None:
    import base64
    import hashlib
    import secrets

    salt = secrets.token_bytes(16)
    legacy = "pbkdf2_sha256$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(
        hashlib.pbkdf2_hmac("sha256", b"old-password-1", salt, 120_000)).decode()
    email = f"legacy-{uuid4().hex[:6]}@example.com"
    with SessionLocal() as db:
        db.add(User(email=email, display_name="legacy", password_hash=legacy))
        db.commit()
    assert verify_password("old-password-1", legacy)
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "old-password-1"}).status_code == 200
    with SessionLocal() as db:
        upgraded = db.scalar(sa.select(User.password_hash).where(User.email == email))
    assert upgraded.count("$") == 3 and verify_password("old-password-1", upgraded)
    assert hash_password("x").startswith("pbkdf2_sha256$1000$")


def test_market_writes_require_admin(client) -> None:
    headers, _ = register(client, "reader")
    symbol = a_symbol()
    payload = {"instrument": {"symbol": symbol, "name": "x"}, "bars": [bar(symbol, "2024-02-01", 10)]}
    assert client.post("/api/v1/market/import", json=payload).status_code == 401
    assert client.post("/api/v1/market/import", headers=headers, json=payload).status_code == 403
    sync = {"provider_id": "demo", "symbol": symbol, "start_date": "2024-03-01", "end_date": "2024-03-05"}
    assert client.post("/api/v1/market/sync", headers=headers, json=sync).status_code == 403


# --------------------------------------------------------------------------- backtests


def test_backtests_require_login_and_are_private(client) -> None:
    strategy = read_json(TEMPLATE_MODULE / "templates" / "price_breakout.json")
    assert client.post("/api/v1/backtests", json={"strategy": strategy}).status_code == 401
    owner, _ = register(client, "owner")
    response = client.post("/api/v1/backtests", headers=owner, json={"strategy": strategy})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "completed" and payload["currency"] == "CNY"
    assert any("not statistically meaningful" in w for w in payload["warnings"])
    backtest_id = payload["backtest_id"]
    assert client.get(f"/api/v1/backtests/{backtest_id}").status_code == 401
    assert client.get(f"/api/v1/backtests/{backtest_id}", headers=owner).status_code == 200
    other, _ = register(client, "other")
    assert client.get(f"/api/v1/backtests/{backtest_id}", headers=other).status_code == 404
    assert client.get(f"/api/v1/backtests/{backtest_id}/report", headers=other).status_code == 404


def test_backtest_reads_bars_imported_through_the_web_app(client, admin_headers) -> None:
    symbol = a_symbol("SZ")
    days = [f"2024-{m:02d}-{d:02d}" for m in range(1, 7) for d in range(1, 29)]
    import datetime as dt

    days = [d for d in days if dt.date.fromisoformat(d).weekday() < 5]
    closes = [10 + (i % 20) * 0.2 for i in range(len(days))]
    imported = client.post("/api/v1/market/import", headers=admin_headers, json={
        "instrument": {"symbol": symbol, "name": "web-imported"},
        "bars": [bar(symbol, d, c) for d, c in zip(days, closes)]})
    assert imported.status_code == 200, imported.text
    strategy = read_json(TEMPLATE_MODULE / "templates" / "rsi_reversal.json")
    strategy["universe"]["symbols"] = [symbol]
    strategy["data"].update({"start_date": "2024-01-01", "end_date": "2024-12-31"})
    user, _ = register(client, "bt")
    result = client.post("/api/v1/backtests", headers=user, json={"strategy": strategy})
    assert result.status_code == 200, result.text
    assert result.json()["metrics"]["bar_count"] == len(days)
    invalid = dict(strategy, market="nasdaq")
    assert client.post("/api/v1/backtests", headers=user, json={"strategy": invalid}).status_code == 400


def test_hk_connect_sync_and_backtest_in_cny(client, admin_headers, monkeypatch) -> None:
    import datetime as dt

    days = []
    day = dt.date(2024, 1, 2)
    while len(days) < 200:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += dt.timedelta(days=1)
    prices = [300 + 20 * ((i // 25) % 2) + (i % 25) for i in range(len(days))]

    def fake_fetch(url, params):
        code = params["param"].split(",")[0]
        a, b = params["param"].split(",")[2:4]
        rows = [[d, f"{p:.3f}", f"{p:.3f}", f"{p * 1.01:.3f}", f"{p * 0.99:.3f}", "1000000", {}]
                for d, p in zip(days, prices) if a <= d <= b]
        if "hkfqkline" in url:  # adjusted: 2 HKD dividend ex on day 100
            rows = [[r[0], *(f"{float(x) - (2 if i < 100 else 0):.3f}" for x in r[1:5]), r[5], {}, "0", "100"]
                    for i, r in enumerate(rows)]
            return {"code": 0, "data": {code: {"qfqday": rows}}}
        return {"code": 0, "data": {code: {"day": rows}}}

    provider = sources.get_provider("tencent")
    monkeypatch.setattr(provider, "fetch_json", fake_fetch, raising=False)
    monkeypatch.setattr(provider, "fetch_name", lambda symbol: "测试港股", raising=False)
    monkeypatch.setattr(provider, "fetch_fx", lambda a, b: {"2024-01-02": 0.9}, raising=False)

    sync = client.post("/api/v1/market/sync", headers=admin_headers, json={
        "provider_id": "tencent", "symbol": "8888.HK", "start_date": days[0], "end_date": days[-1]})
    assert sync.status_code == 200, sync.text
    body = sync.json()
    assert body["symbol"] == "08888.HK" and body["fetched_bars"] == 200
    assert body["corporate_actions"] == 1 and body["fx_rates"] == 1
    instrument = client.get("/api/v1/market/instruments/08888.HK").json()
    assert instrument["market"] == "hk_stock" and instrument["currency"] == "HKD"
    actions = client.get("/api/v1/market/corporate-actions/08888.HK").json()["actions"]
    assert actions[0]["cash_dividend"] == pytest.approx(2.0) and actions[0]["ex_date"] == days[100]

    strategy = read_json(TEMPLATE_MODULE / "templates" / "hk_connect_ma_trend.json")
    strategy["universe"]["symbols"] = ["08888.HK"]
    strategy["data"].update({"start_date": days[0], "end_date": days[-1]})
    strategy["entry"]["conditions"][0]["right"]["params"]["period"] = 30
    strategy["exit"]["conditions"][0]["right"]["params"]["period"] = 30
    user, _ = register(client, "connect")
    result = client.post("/api/v1/backtests", headers=user, json={"strategy": strategy})
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["market"] == "hk_connect" and payload["currency"] == "CNY"
    assert any("board lot" in w for w in payload["warnings"])  # no lot size known yet
    report = client.get(f"/api/v1/backtests/{payload['backtest_id']}", headers=user).json()
    assert report["quote_currency"] == "HKD"
    assert all(t["entry_fx"] == pytest.approx(0.9) for t in report["trades"])


# --------------------------------------------------------------------------- market data


def test_market_data_browser_endpoints(client) -> None:
    instruments = client.get("/api/v1/market/instruments").json()["instruments"]
    assert len(instruments) >= 1
    symbol = instruments[0]["symbol"]
    assert instruments[0]["bar_count"] >= 1 and instruments[0]["currency"] in {"CNY", "HKD"}
    assert client.get(f"/api/v1/market/instruments/{symbol}").json()["symbol"] == symbol
    bars = client.get(f"/api/v1/market/bars?symbol={symbol}&frequency=1d&limit=5").json()
    assert bars["symbol"] == symbol and len(bars["bars"]) >= 1
    coverage = client.get("/api/v1/market/coverage").json()
    assert coverage["market"] == "multi" and coverage["instrument_count"] >= 1


def test_admin_market_data_import_flow(client, admin_headers) -> None:
    symbol = a_symbol()
    payload = {"instrument": {"symbol": symbol, "name": "测试导入股票", "exchange": "SH"},
               "bars": [bar(symbol, "2024-02-01", 10.5)]}
    response = client.post("/api/v1/market/import", headers=admin_headers, json=payload)
    assert response.status_code == 200 and response.json()["inserted_bars"] == 1
    payload["bars"][0]["close"] = 10.6
    payload["bars"][0]["high"] = 10.7
    assert client.post("/api/v1/market/import", headers=admin_headers, json=payload).json()["updated_bars"] == 1
    assert client.get(f"/api/v1/market/bars?symbol={symbol}&frequency=1d&limit=1").json()["bars"][0]["close"] == 10.6
    assert client.get(f"/api/v1/market/quality?symbol={symbol}").json()["issue_count"] == 0
    imports = client.get("/api/v1/market/imports", headers=admin_headers).json()["imports"]
    assert any(item["symbol"] == symbol and item["import_type"] == "manual" for item in imports)

    wrong = {"instrument": {"symbol": symbol, "name": "x", "exchange": "SZ"}, "bars": []}
    assert client.post("/api/v1/market/import", headers=admin_headers, json=wrong).status_code == 400
    bad_symbol = {"instrument": {"symbol": "TEST.SH", "name": "x"}, "bars": []}
    assert client.post("/api/v1/market/import", headers=admin_headers, json=bad_symbol).status_code == 400


def test_hk_instrument_import_keeps_board_lot(client, admin_headers) -> None:
    symbol = a_symbol("HK")
    payload = {"instrument": {"symbol": symbol, "name": "港股", "lot_size": 2000}, "bars": [bar(symbol, "2024-02-01", 40)]}
    assert client.post("/api/v1/market/import", headers=admin_headers, json=payload).status_code == 200
    payload["instrument"].pop("lot_size")
    assert client.post("/api/v1/market/import", headers=admin_headers, json=payload).status_code == 200
    detail = client.get(f"/api/v1/market/instruments/{symbol}").json()
    assert (detail["lot_size"], detail["currency"], detail["exchange"]) == (2000, "HKD", "HK")


def test_market_quality_detects_enhanced_issues(client, admin_headers) -> None:
    symbol = a_symbol()
    response = client.post("/api/v1/market/import", headers=admin_headers, json={
        "instrument": {"symbol": symbol, "name": "质量测试股票"},
        "bars": [{"symbol": symbol, "frequency": "1d", "trade_time": "2024-05-06", "open": 10, "high": 9,
                  "low": 11, "close": -1, "volume": -10, "amount": 0}]})
    assert response.status_code == 200
    quality = client.get(f"/api/v1/market/quality?symbol={symbol}").json()
    assert quality["quality_score"] < 100 and quality["error_count"] >= 1
    assert quality["issue_summary"]["non_positive_price"] == 1
    assert quality["issue_summary"]["invalid_high_low"] == 1


def test_market_quality_uses_each_markets_calendar(client, admin_headers) -> None:
    a = a_symbol()
    client.post("/api/v1/market/import", headers=admin_headers, json={
        "instrument": {"symbol": a, "name": "A"}, "bars": [bar(a, "2024-03-01", 10), bar(a, "2024-03-05", 10)]})
    quality = client.get(f"/api/v1/market/quality?symbol={a}").json()
    assert quality["calendar_name"].startswith("XSHG")
    assert quality["missing_trading_days"] == ["2024-03-04"]

    spring = a_symbol()
    client.post("/api/v1/market/import", headers=admin_headers, json={
        "instrument": {"symbol": spring, "name": "A2025"}, "bars": [bar(spring, "2025-01-27", 10), bar(spring, "2025-02-05", 10)]})
    assert client.get(f"/api/v1/market/quality?symbol={spring}").json()["missing_trading_days"] == []  # 2025 holiday

    hk = a_symbol("HK")
    client.post("/api/v1/market/import", headers=admin_headers, json={
        "instrument": {"symbol": hk, "name": "HK"}, "bars": [bar(hk, "2024-12-24", 10), bar(hk, "2024-12-27", 10)]})
    quality = client.get(f"/api/v1/market/quality?symbol={hk}").json()
    assert quality["calendar_name"].startswith("XHKG") and quality["missing_trading_days"] == []  # Christmas


def test_demo_data_source_sync_flow(client, admin_headers) -> None:
    sources_list = client.get("/api/v1/market/data-sources").json()["sources"]
    assert {item["provider_id"] for item in sources_list} == {"tencent", "demo"}
    symbol = a_symbol()
    response = client.post("/api/v1/market/sync", headers=admin_headers, json={
        "provider_id": "demo", "symbol": symbol, "start_date": "2024-03-01", "end_date": "2024-03-05", "frequency": "1d"})
    assert response.status_code == 200
    assert response.json()["fetched_bars"] == 3 and response.json()["inserted_bars"] == 3
    bars = client.get(f"/api/v1/market/bars?symbol={symbol}&frequency=1d&limit=5").json()["bars"]
    assert {b["source"] for b in bars} == {"demo"}
    imported = next(i for i in client.get("/api/v1/market/imports", headers=admin_headers).json()["imports"] if i["symbol"] == symbol)
    assert imported["import_type"] == "data_source_sync"
    unsupported = client.post("/api/v1/market/sync", headers=admin_headers, json={
        "provider_id": "demo", "symbol": symbol, "start_date": "2024-03-01", "end_date": "2024-03-05", "frequency": "60m"})
    assert unsupported.status_code == 400


def test_admin_market_csv_import_flow(client, admin_headers) -> None:
    symbol = a_symbol("SZ")
    response = client.post("/api/v1/market/import/csv", headers=admin_headers, json={
        "symbol": symbol, "name": "CSV导入股票", "exchange": "SZ", "frequency": "1d",
        "csv_text": "trade_time,open,high,low,close,volume,amount\n2024-03-01,20,21,19.5,20.8,1000,20800\n"
                    "2024-03-04,20.8,22,20.2,21.5,1200,25800\n"})
    assert response.status_code == 200
    assert (response.json()["parsed_rows"], response.json()["inserted_bars"], response.json()["skipped_rows"]) == (2, 2, 0)
    imported = next(i for i in client.get("/api/v1/market/imports", headers=admin_headers).json()["imports"] if i["symbol"] == symbol)
    assert imported["import_type"] == "csv" and imported["inserted_bars"] == 2
    detail = client.get(f"/api/v1/market/imports/{imported['id']}", headers=admin_headers).json()
    assert detail["status"] == "completed" and detail["payload"]["parsed_rows"] == 2

    invalid = client.post("/api/v1/market/import/csv", headers=admin_headers, json={
        "symbol": symbol, "name": "CSV导入股票", "csv_text": "trade_time,close\n2024-03-05,22.1\n"})
    assert invalid.status_code == 400
    failed = next(i for i in client.get("/api/v1/market/imports", headers=admin_headers).json()["imports"]
                  if i["symbol"] == symbol and i["status"] == "failed")
    assert client.get(f"/api/v1/market/imports/{failed['id']}", headers=admin_headers).json()["errors"]
    other, _ = register(client, "nosy")
    assert client.get(f"/api/v1/market/imports/{failed['id']}", headers=other).status_code == 404


def test_admin_market_csv_file_upload_flow_and_size_limit(client, admin_headers, monkeypatch) -> None:
    symbol = a_symbol()
    content = "trade_time,open,high,low,close,volume,amount\n2024-04-01,30,31,29.5,30.8,1000,30800\n"
    upload = client.post("/api/v1/market/import/file", headers=admin_headers,
                         data={"symbol": symbol, "name": "文件导入股票", "frequency": "1d"},
                         files={"file": ("bars.csv", content, "text/csv")})
    assert upload.status_code == 200 and upload.json()["inserted_bars"] == 1
    imported = next(i for i in client.get("/api/v1/market/imports", headers=admin_headers).json()["imports"] if i["symbol"] == symbol)
    assert client.get(f"/api/v1/market/imports/{imported['id']}", headers=admin_headers).json()["source"] == "bars.csv"

    wrong = client.post("/api/v1/market/import/file", headers=admin_headers, data={"symbol": symbol, "name": "x"},
                        files={"file": ("bars.txt", content, "text/plain")})
    assert wrong.status_code == 400

    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 64)
    too_big = client.post("/api/v1/market/import/file", headers=admin_headers, data={"symbol": symbol, "name": "x"},
                          files={"file": ("bars.csv", content * 3, "text/csv")})
    assert too_big.status_code == 413
    monkeypatch.setattr(settings, "max_import_bars", 1)
    many = {"instrument": {"symbol": symbol, "name": "x"}, "bars": [bar(symbol, "2024-04-02", 1), bar(symbol, "2024-04-03", 1)]}
    assert client.post("/api/v1/market/import", headers=admin_headers, json=many).status_code == 413


def test_import_history_is_not_hidden_by_other_users_imports(client, admin_headers) -> None:
    from app.services.market_service import record_market_import_batch

    user_headers, user = register(client, "history")
    with SessionLocal() as db:
        record_market_import_batch(db, owner_id=user["user"]["id"], import_type="manual",
                                   result={"symbol": "600000.SH", "message": "mine"})
        for _ in range(25):
            record_market_import_batch(db, owner_id=1, import_type="manual", result={"symbol": "600001.SH", "message": "x"})
    mine = client.get("/api/v1/market/imports?limit=20", headers=user_headers).json()["imports"]
    assert [i["symbol"] for i in mine] == ["600000.SH"]


def test_review_regressions(client, admin_headers) -> None:
    # FX rates must be positive dates/values
    bad_fx = client.post("/api/v1/market/fx", headers=admin_headers, json={"pair": "HKDCNY", "rates": {"2024-01-02": 0}})
    assert bad_fx.status_code == 400
    # chunked body above the limit is rejected before parsing
    from app.core.config import settings

    def body():
        for _ in range(8):
            yield b"x" * (1024 * 1024)

    old = settings.max_upload_bytes
    settings.max_upload_bytes = 1024
    try:
        response = client.post("/api/v1/market/import/csv", headers={**admin_headers, "content-type": "application/json"}, content=body())
        assert response.status_code == 413
    finally:
        settings.max_upload_bytes = old
    # another user's strategy cannot be referenced
    owner, _ = register(client, "stratowner")
    strategy = read_json(TEMPLATE_MODULE / "templates" / "price_breakout.json")
    created = client.post("/api/v1/strategies", headers=owner, json={"name": "mine", "strategy": strategy}).json()
    intruder, _ = register(client, "intruder")
    leaked = client.post("/api/v1/backtests", headers=intruder, json={"strategy": strategy, "source_strategy_id": created["strategy_id"]})
    assert leaked.status_code == 404


def test_resync_keeps_earlier_dividends(client, admin_headers) -> None:
    symbol = a_symbol()
    days = ["2024-01-02", "2024-01-03", "2024-06-03", "2024-06-04"]
    closes = [10.0, 9.8, 10.0, 9.5]
    client.post("/api/v1/market/import", headers=admin_headers, json={
        "instrument": {"symbol": symbol, "name": "x"}, "bars": [bar(symbol, d, c) for d, c in zip(days, closes)]})
    from app.services.market_service import import_corporate_actions

    with SessionLocal() as db:
        import_corporate_actions(db, symbol, [{"ex_date": "2024-01-03", "cash_dividend": 0.2}], "tencent_derived", "2024-01-01", "2024-01-31")
        import_corporate_actions(db, symbol, [{"ex_date": "2024-06-04", "cash_dividend": 0.5}], "tencent_derived", "2024-06-01", "2024-06-30")
    actions = client.get(f"/api/v1/market/corporate-actions/{symbol}").json()["actions"]
    assert [a["ex_date"] for a in actions] == ["2024-01-03", "2024-06-04"]
    factors = [b["adj_factor"] for b in client.get(f"/api/v1/market/bars?symbol={symbol}&limit=10").json()["bars"]]
    assert factors[-1] == 1.0 and factors[2] == 0.95 and factors[0] < factors[1]


# --------------------------------------------------------------------------- persistence


def test_user_account_and_strategy_persistence_flow(client) -> None:
    strategy = read_json(TEMPLATE_MODULE / "templates" / "price_breakout.json")
    headers, payload = register(client, "tester")
    assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == payload["user"]["email"]
    created = client.post("/api/v1/strategies", headers=headers, json={
        "name": "My price breakout", "strategy": strategy, "source_template_id": "tpl_price_breakout"})
    assert created.status_code == 201
    created = created.json()
    assert created["status"] == "draft"
    assert len(client.get("/api/v1/strategies", headers=headers).json()["strategies"]) == 1
    updated = client.put(f"/api/v1/strategies/{created['strategy_id']}", headers=headers, json={
        "name": "My active breakout", "status": "active", "strategy": strategy, "change_note": "Promote"})
    assert updated.status_code == 200 and updated.json()["status"] == "active"
    assert len(client.get(f"/api/v1/strategies/{created['strategy_id']}/versions", headers=headers).json()["versions"]) == 2
    backtest = client.post("/api/v1/backtests", headers=headers, json={"strategy": strategy, "source_strategy_id": created["strategy_id"]})
    assert backtest.status_code == 200
    backtest_id = backtest.json()["backtest_id"]
    stored = next(i for i in client.get("/api/v1/backtests", headers=headers).json()["backtests"] if i["backtest_id"] == backtest_id)
    assert stored["source_strategy_id"] == created["strategy_id"] and stored["strategy_version"] == 2
    assert stored["parameter_snapshot"]["symbol"] == "600519.SH"
    mine = client.get(f"/api/v1/backtests/mine/{backtest_id}", headers=headers).json()
    assert mine["strategy"]["strategy_id"] == strategy["strategy_id"]
    assert client.delete(f"/api/v1/strategies/{created['strategy_id']}", headers=headers).status_code == 204


# --------------------------------------------------------------------------- backup / restore


def test_backup_excludes_sessions_and_restores(client, admin_headers, tmp_path) -> None:
    with SessionLocal() as db:
        result = create_database_backup(db, output_dir=tmp_path)
        assert "user_sessions" not in result["row_counts"]
        assert result["row_counts"]["strategy_templates"] >= 7
        metadata = read_backup_metadata(result["backup_path"])
        assert metadata["metadata"]["format_version"] == "2.0"
        with gzip.open(result["backup_path"], "rt", encoding="utf-8") as handle:
            assert "user_sessions" not in json.load(handle)["tables"]
        users_before = db.scalar(sa.select(sa.func.count()).select_from(User))
        restored = restore_database_backup(db, result["backup_path"])
        assert restored["restored_rows"]["users"] == users_before
        assert db.scalar(sa.select(sa.func.count()).select_from(UserSession)) == 0
    # sessions were dropped by the restore; log in again
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 401


def test_restore_of_v1_backup_keeps_an_admin(client, tmp_path) -> None:
    with SessionLocal() as db:
        result = create_database_backup(db, output_dir=tmp_path)
    with gzip.open(result["backup_path"], "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["metadata"]["format_version"] = "1.0"
    for table in ("market_corporate_actions", "market_fx_rates"):
        payload["tables"].pop(table, None)
    for row in payload["tables"]["users"]:
        row.pop("is_admin", None)
    old = tmp_path / "v1.json.gz"
    with gzip.open(old, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    with SessionLocal() as db:
        restore_database_backup(db, old)
        assert db.scalar(sa.select(sa.func.count()).select_from(User).where(User.is_admin.is_(True))) == 1

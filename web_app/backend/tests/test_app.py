from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.services.json_utils import read_json
from app.services.legacy_paths import TEMPLATE_MODULE


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_status_blocks_live_trading() -> None:
    response = client.get("/api/v1/security/status")
    assert response.status_code == 200
    assert response.json()["live_trading_status"] == "blocked_for_live_trading"


def test_templates_list() -> None:
    response = client.get("/api/v1/templates")
    assert response.status_code == 200
    assert len(response.json()["templates"]) >= 1


def test_strategy_validation() -> None:
    strategy = read_json(TEMPLATE_MODULE / "templates" / "price_breakout.json")
    response = client.post("/api/v1/strategies/validate", json={"strategy": strategy})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_backtest_run() -> None:
    strategy = read_json(TEMPLATE_MODULE / "templates" / "price_breakout.json")
    response = client.post("/api/v1/backtests", json={"strategy": strategy})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["metrics"]["trade_count"] >= 0


def test_database_init_and_status() -> None:
    init_response = client.post("/api/v1/database/init")
    assert init_response.status_code == 200
    init_payload = init_response.json()
    assert init_payload["database"] == "ready"
    assert init_payload["tables"]["strategy_templates"] >= 1
    assert init_payload["tables"]["market_instruments"] >= 1
    assert init_payload["tables"]["backtest_runs"] >= 1

    status_response = client.get("/api/v1/database/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["table_count"] >= 7
    assert status_payload["tables"]["market_bars"] >= 1


def test_market_data_browser_endpoints() -> None:
    client.post("/api/v1/database/init")

    instruments_response = client.get("/api/v1/market/instruments")
    assert instruments_response.status_code == 200
    instruments = instruments_response.json()["instruments"]
    assert len(instruments) >= 1
    symbol = instruments[0]["symbol"]
    assert instruments[0]["bar_count"] >= 1

    detail_response = client.get(f"/api/v1/market/instruments/{symbol}")
    assert detail_response.status_code == 200
    assert detail_response.json()["symbol"] == symbol

    bars_response = client.get(f"/api/v1/market/bars?symbol={symbol}&frequency=1d&limit=5")
    assert bars_response.status_code == 200
    bars_payload = bars_response.json()
    assert bars_payload["symbol"] == symbol
    assert len(bars_payload["bars"]) >= 1

    coverage_response = client.get("/api/v1/market/coverage")
    assert coverage_response.status_code == 200
    coverage_payload = coverage_response.json()
    assert coverage_payload["instrument_count"] >= 1
    assert coverage_payload["total_bar_count"] >= 1


def test_authenticated_market_data_import_flow() -> None:
    email = f"market-{uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "strong-password-123",
            "display_name": "Market Manager",
        },
    )
    assert register_response.status_code == 200
    headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}
    symbol = f"TEST{uuid4().hex[:4].upper()}.SH"
    payload = {
        "instrument": {
            "symbol": symbol,
            "name": "测试导入股票",
            "exchange": "SH",
        },
        "bars": [
            {
                "symbol": symbol,
                "frequency": "1d",
                "trade_time": "2024-02-01",
                "open": 10.0,
                "high": 10.8,
                "low": 9.8,
                "close": 10.5,
                "volume": 1000,
                "amount": 10500,
            }
        ],
    }

    import_response = client.post("/api/v1/market/import", headers=headers, json=payload)
    assert import_response.status_code == 200
    assert import_response.json()["inserted_bars"] == 1

    payload["bars"][0]["close"] = 10.6
    update_response = client.post("/api/v1/market/import", headers=headers, json=payload)
    assert update_response.status_code == 200
    assert update_response.json()["updated_bars"] == 1

    bars_response = client.get(f"/api/v1/market/bars?symbol={symbol}&frequency=1d&limit=1")
    assert bars_response.status_code == 200
    assert bars_response.json()["bars"][0]["close"] == 10.6

    quality_response = client.get(f"/api/v1/market/quality?symbol={symbol}")
    assert quality_response.status_code == 200
    assert quality_response.json()["issue_count"] == 0

    imports_response = client.get("/api/v1/market/imports", headers=headers)
    assert imports_response.status_code == 200
    imports = imports_response.json()["imports"]
    assert any(item["symbol"] == symbol and item["import_type"] == "manual" for item in imports)


def test_authenticated_market_csv_import_flow() -> None:
    email = f"csv-{uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "strong-password-123",
            "display_name": "CSV Manager",
        },
    )
    assert register_response.status_code == 200
    headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}
    symbol = f"CSV{uuid4().hex[:4].upper()}.SZ"

    import_response = client.post(
        "/api/v1/market/import/csv",
        headers=headers,
        json={
            "symbol": symbol,
            "name": "CSV导入股票",
            "exchange": "SZ",
            "frequency": "1d",
            "csv_text": (
                "trade_time,open,high,low,close,volume,amount\n"
                "2024-03-01,20,21,19.5,20.8,1000,20800\n"
                "2024-03-04,20.8,22,20.2,21.5,1200,25800\n"
            ),
        },
    )
    assert import_response.status_code == 200
    payload = import_response.json()
    assert payload["parsed_rows"] == 2
    assert payload["inserted_bars"] == 2
    assert payload["skipped_rows"] == 0

    bars_response = client.get(f"/api/v1/market/bars?symbol={symbol}&frequency=1d&limit=5")
    assert bars_response.status_code == 200
    assert len(bars_response.json()["bars"]) == 2

    imports_response = client.get("/api/v1/market/imports", headers=headers)
    assert imports_response.status_code == 200
    imports = imports_response.json()["imports"]
    imported = next(item for item in imports if item["symbol"] == symbol)
    assert imported["import_type"] == "csv"
    assert imported["inserted_bars"] == 2

    detail_response = client.get(f"/api/v1/market/imports/{imported['id']}", headers=headers)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["symbol"] == symbol
    assert detail_payload["status"] == "completed"
    assert detail_payload["payload"]["parsed_rows"] == 2

    invalid_response = client.post(
        "/api/v1/market/import/csv",
        headers=headers,
        json={
            "symbol": symbol,
            "name": "CSV导入股票",
            "exchange": "SZ",
            "csv_text": "trade_time,close\n2024-03-05,22.1\n",
        },
    )
    assert invalid_response.status_code == 400

    failed_imports_response = client.get("/api/v1/market/imports", headers=headers)
    assert failed_imports_response.status_code == 200
    failed_import = next(
        item
        for item in failed_imports_response.json()["imports"]
        if item["symbol"] == symbol and item["status"] == "failed"
    )
    failed_detail_response = client.get(f"/api/v1/market/imports/{failed_import['id']}", headers=headers)
    assert failed_detail_response.status_code == 200
    assert failed_detail_response.json()["errors"]


def test_authenticated_market_csv_file_upload_flow() -> None:
    email = f"file-{uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "strong-password-123",
            "display_name": "File Manager",
        },
    )
    assert register_response.status_code == 200
    headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}
    symbol = f"FIL{uuid4().hex[:4].upper()}.SH"
    csv_content = (
        "trade_time,open,high,low,close,volume,amount\n"
        "2024-04-01,30,31,29.5,30.8,1000,30800\n"
    )

    upload_response = client.post(
        "/api/v1/market/import/file",
        headers=headers,
        data={
            "symbol": symbol,
            "name": "文件导入股票",
            "exchange": "SH",
            "frequency": "1d",
        },
        files={"file": ("bars.csv", csv_content, "text/csv")},
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["parsed_rows"] == 1
    assert upload_response.json()["inserted_bars"] == 1

    imports_response = client.get("/api/v1/market/imports", headers=headers)
    assert imports_response.status_code == 200
    imported = next(item for item in imports_response.json()["imports"] if item["symbol"] == symbol)
    assert imported["import_type"] == "csv_file"
    detail_response = client.get(f"/api/v1/market/imports/{imported['id']}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["source"] == "bars.csv"

    wrong_file_response = client.post(
        "/api/v1/market/import/file",
        headers=headers,
        data={
            "symbol": symbol,
            "name": "文件导入股票",
            "exchange": "SH",
        },
        files={"file": ("bars.txt", csv_content, "text/plain")},
    )
    assert wrong_file_response.status_code == 400
    failed_imports_response = client.get("/api/v1/market/imports", headers=headers)
    failed_import = next(
        item
        for item in failed_imports_response.json()["imports"]
        if item["symbol"] == symbol and item["status"] == "failed"
    )
    assert failed_import["import_type"] == "csv_file"


def test_user_account_and_strategy_persistence_flow() -> None:
    strategy = read_json(TEMPLATE_MODULE / "templates" / "price_breakout.json")
    email = f"tester-{uuid4().hex[:8]}@example.com"

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "strong-password-123",
            "display_name": "Strategy Tester",
        },
    )
    assert register_response.status_code == 200
    token = register_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_response = client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == email

    create_response = client.post(
        "/api/v1/strategies",
        headers=headers,
        json={
            "name": "My price breakout",
            "strategy": strategy,
            "source_template_id": "tpl_price_breakout",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "My price breakout"
    assert created["status"] == "draft"

    list_response = client.get("/api/v1/strategies", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["strategies"]) == 1

    strategy["data"]["frequency"] = "1d"
    update_response = client.put(
        f"/api/v1/strategies/{created['strategy_id']}",
        headers=headers,
        json={
            "name": "My active breakout",
            "status": "active",
            "strategy": strategy,
            "change_note": "Promote draft to active",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "active"

    versions_response = client.get(
        f"/api/v1/strategies/{created['strategy_id']}/versions",
        headers=headers,
    )
    assert versions_response.status_code == 200
    assert len(versions_response.json()["versions"]) == 2

    backtest_response = client.post(
        "/api/v1/backtests",
        headers=headers,
        json={"strategy": strategy, "source_strategy_id": created["strategy_id"]},
    )
    assert backtest_response.status_code == 200
    backtest_id = backtest_response.json()["backtest_id"]

    backtests_response = client.get("/api/v1/backtests", headers=headers)
    assert backtests_response.status_code == 200
    backtests = backtests_response.json()["backtests"]
    assert any(item["backtest_id"] == backtest_id for item in backtests)
    stored_backtest = next(item for item in backtests if item["backtest_id"] == backtest_id)
    assert stored_backtest["source_strategy_id"] == created["strategy_id"]
    assert stored_backtest["strategy_version"] == 2
    assert stored_backtest["parameter_snapshot"]["symbol"] == "600519.SH"

    my_report_response = client.get(f"/api/v1/backtests/mine/{backtest_id}", headers=headers)
    assert my_report_response.status_code == 200
    assert my_report_response.json()["metrics"]["trade_count"] >= 0
    assert my_report_response.json()["strategy"]["strategy_id"] == strategy["strategy_id"]

    delete_response = client.delete(f"/api/v1/strategies/{created['strategy_id']}", headers=headers)
    assert delete_response.status_code == 204

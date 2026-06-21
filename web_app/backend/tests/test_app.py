from fastapi.testclient import TestClient

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

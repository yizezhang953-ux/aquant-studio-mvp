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

    delete_response = client.delete(f"/api/v1/strategies/{created['strategy_id']}", headers=headers)
    assert delete_response.status_code == 204

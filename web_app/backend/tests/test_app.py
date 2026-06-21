from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_status_blocks_live_trading() -> None:
    response = client.get("/api/v1/security/status")
    assert response.status_code == 200
    assert response.json()["live_trading_status"] == "blocked_for_live_trading"

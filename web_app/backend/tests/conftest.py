"""Isolated test database and fast password hashing, set before the app is imported."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="aquant-test-"))
# TEST_DATABASE_URL=postgresql+psycopg://... runs the suite against PostgreSQL (use an empty database).
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["PASSWORD_HASH_ITERATIONS"] = "1000"
os.environ["BACKUP_DIR"] = str(_TMP / "backups")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.auth_service import reset_login_throttle, set_admin  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:  # runs startup: migrations + seed
        yield test_client


@pytest.fixture(scope="session")
def admin_headers(client):
    response = client.post("/api/v1/auth/register", json={
        "email": "admin@example.com", "password": "admin-password-123", "display_name": "Admin"})
    if response.status_code == 409:
        response = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:  # what an operator does with `database_maintenance make-admin`
        set_admin(db, "admin@example.com")
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _clear_throttle():
    reset_login_throttle()
    yield

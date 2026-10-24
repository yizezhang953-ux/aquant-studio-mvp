import json

import sqlalchemy as sa
from alembic import command

from app.services.database_service import _alembic_config, run_migrations


def _engine(tmp_path, name):
    return sa.create_engine(f"sqlite:///{(tmp_path / name).as_posix()}")


def test_fresh_database_is_created_at_head(tmp_path):
    engine = _engine(tmp_path, "fresh.db")
    run_migrations(engine)
    inspector = sa.inspect(engine)
    assert {"market_fx_rates", "market_corporate_actions", "users"} <= set(inspector.get_table_names())
    with engine.connect() as conn:
        assert conn.execute(sa.text("select version_num from alembic_version")).scalar() == "0002"


def test_unversioned_v01_database_is_stamped_and_upgraded(tmp_path):
    engine = _engine(tmp_path, "legacy.db")
    config = _alembic_config()
    with engine.begin() as conn:  # build the v0.1 schema, then forget the version like create_all() did
        config.attributes["connection"] = conn
        command.upgrade(config, "0001")
    with engine.begin() as conn:
        conn.execute(sa.text("drop table alembic_version"))
        conn.execute(sa.text("insert into users(id, email, display_name, password_hash, is_active, created_at, updated_at) "
                             "values (1, 'old@example.com', 'old', 'x', 1, current_timestamp, current_timestamp)"))
        conn.execute(sa.text("insert into user_sessions(user_id, token, expires_at, created_at) "
                             "values (1, 'plaintext-token', '2999-01-01 00:00:00', current_timestamp)"))
        conn.execute(sa.text("insert into audit_logs(event_type, status, message, payload_json, created_at) "
                             "values ('market_import', 'completed', '', :p, current_timestamp)"),
                     {"p": json.dumps({"owner_id": 1, "symbol": "600519.SH"})})
    run_migrations(engine)
    with engine.connect() as conn:
        assert conn.execute(sa.text("select version_num from alembic_version")).scalar() == "0002"
        assert conn.execute(sa.text("select is_admin from users where id = 1")).scalar() == 1
        assert conn.execute(sa.text("select revoked_at from user_sessions")).scalar() is not None
        assert conn.execute(sa.text("select owner_id from audit_logs")).scalar() == 1
    columns = {c["name"] for c in sa.inspect(engine).get_columns("market_instruments")}
    assert {"currency", "lot_size", "connect_eligible"} <= columns
    run_migrations(engine)  # idempotent

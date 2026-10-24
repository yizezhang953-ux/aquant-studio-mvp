"""Alembic environment. The database URL comes from app settings (DATABASE_URL), not alembic.ini."""
from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.session import Base, database_url

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        _run(connectable)
        return
    engine = engine_from_config({"sqlalchemy.url": database_url}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""multi-market, admin role, hashed tokens

* market_instruments: currency, lot_size (HK board lot), connect_eligible (港股通)
* market_corporate_actions, market_fx_rates: dividends / bonus shares and HKD->CNY rates
* users.is_admin (the earliest existing user becomes admin), audit_logs.owner_id (backfilled)
* user_sessions now store a SHA-256 of the token: existing plaintext sessions are revoked

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 11:57:58.107345
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded so it also applies cleanly to databases that were first created with create_all().
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    def columns(table: str) -> set[str]:
        return {c["name"] for c in inspector.get_columns(table)} if table in tables else set()

    if "market_fx_rates" not in tables:
        op.create_table('market_fx_rates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pair', sa.String(length=12), nullable=False),
        sa.Column('rate_date', sa.String(length=20), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pair', 'rate_date', name='uq_fx_rate_identity')
        )
        with op.batch_alter_table('market_fx_rates', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_market_fx_rates_pair'), ['pair'], unique=False)
            batch_op.create_index(batch_op.f('ix_market_fx_rates_rate_date'), ['rate_date'], unique=False)

    if "market_corporate_actions" not in tables:
        op.create_table('market_corporate_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=40), nullable=False),
        sa.Column('ex_date', sa.String(length=20), nullable=False),
        sa.Column('cash_dividend', sa.Float(), nullable=False),
        sa.Column('bonus_ratio', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('source', sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(['symbol'], ['market_instruments.symbol'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', 'ex_date', 'source', name='uq_corporate_action_identity')
        )
        with op.batch_alter_table('market_corporate_actions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_market_corporate_actions_ex_date'), ['ex_date'], unique=False)
            batch_op.create_index(batch_op.f('ix_market_corporate_actions_symbol'), ['symbol'], unique=False)

    if "owner_id" not in columns("audit_logs"):
        with op.batch_alter_table('audit_logs', schema=None) as batch_op:
            batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f('ix_audit_logs_owner_id'), ['owner_id'], unique=False)
            batch_op.create_foreign_key('fk_audit_logs_owner_id_users', 'users', ['owner_id'], ['id'])

    instrument_columns = columns("market_instruments")
    with op.batch_alter_table('market_instruments', schema=None) as batch_op:
        if "currency" not in instrument_columns:
            batch_op.add_column(sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False))
        if "lot_size" not in instrument_columns:
            batch_op.add_column(sa.Column('lot_size', sa.Integer(), nullable=True))
        if "connect_eligible" not in instrument_columns:
            batch_op.add_column(sa.Column('connect_eligible', sa.Boolean(), nullable=True))

    if "is_admin" not in columns("users"):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_admin', sa.Boolean(), server_default='0', nullable=False))

    # ### end Alembic commands ###
    bind = op.get_bind()
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("is_admin", sa.Boolean))
    first_id = bind.execute(sa.select(sa.func.min(users.c.id))).scalar()
    if first_id is not None:
        bind.execute(users.update().where(users.c.id == first_id).values(is_admin=True))

    sessions = sa.table("user_sessions", sa.column("revoked_at", sa.DateTime))
    bind.execute(sessions.update().where(sessions.c.revoked_at.is_(None)).values(revoked_at=sa.func.now()))

    audit = sa.table("audit_logs", sa.column("id", sa.Integer), sa.column("event_type", sa.String),
                     sa.column("payload_json", sa.JSON), sa.column("owner_id", sa.Integer))
    rows = bind.execute(sa.select(audit.c.id, audit.c.payload_json).where(audit.c.event_type == "market_import")).all()
    for row_id, payload in rows:
        if isinstance(payload, str):
            payload = json.loads(payload)
        owner = (payload or {}).get("owner_id")
        if isinstance(owner, int):
            bind.execute(audit.update().where(audit.c.id == row_id).values(owner_id=owner))


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_admin')

    with op.batch_alter_table('market_instruments', schema=None) as batch_op:
        batch_op.drop_column('connect_eligible')
        batch_op.drop_column('lot_size')
        batch_op.drop_column('currency')

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_audit_logs_owner_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_audit_logs_owner_id'))
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('market_corporate_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_market_corporate_actions_symbol'))
        batch_op.drop_index(batch_op.f('ix_market_corporate_actions_ex_date'))

    op.drop_table('market_corporate_actions')
    with op.batch_alter_table('market_fx_rates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_market_fx_rates_rate_date'))
        batch_op.drop_index(batch_op.f('ix_market_fx_rates_pair'))

    op.drop_table('market_fx_rates')
    # ### end Alembic commands ###

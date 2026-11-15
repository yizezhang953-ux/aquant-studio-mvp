"""sector_daily / data_credentials: sector panel data for rotation backtests, vendor API tokens

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "sector_daily" not in tables:
        op.create_table('sector_daily',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('universe', sa.String(length=40), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('trade_date', sa.String(length=10), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=True),
        sa.Column('float_mv', sa.Float(), nullable=True),
        sa.Column('buy_amount', sa.Float(), nullable=True),
        sa.Column('sell_amount', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('universe', 'code', 'trade_date', name='uq_sector_daily')
        )
        with op.batch_alter_table('sector_daily', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_sector_daily_universe'), ['universe'], unique=False)
            batch_op.create_index(batch_op.f('ix_sector_daily_trade_date'), ['trade_date'], unique=False)
    if "data_credentials" not in tables:
        op.create_table('data_credentials',
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('secret', sa.String(length=500), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('provider')
        )


def downgrade() -> None:
    op.drop_table('data_credentials')
    op.drop_table('sector_daily')

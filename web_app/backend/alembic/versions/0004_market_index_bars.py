"""market_index_bars: daily closes of benchmark indices (沪深300, 恒生指数) for reports

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "market_index_bars" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('market_index_bars',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('index_code', sa.String(length=20), nullable=False),
    sa.Column('trade_date', sa.String(length=10), nullable=False),
    sa.Column('close', sa.Float(), nullable=False),
    sa.Column('source', sa.String(length=40), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('index_code', 'trade_date', name='uq_index_bar_identity')
    )
    with op.batch_alter_table('market_index_bars', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_market_index_bars_index_code'), ['index_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_market_index_bars_trade_date'), ['trade_date'], unique=False)


def downgrade() -> None:
    op.drop_table('market_index_bars')

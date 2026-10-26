"""paper_accounts: virtual-money accounts that follow a strategy forward in time

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26 16:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "paper_accounts" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('paper_accounts',
    sa.Column('account_id', sa.String(length=40), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('source_strategy_id', sa.String(length=120), nullable=True),
    sa.Column('strategy_json', sa.JSON(), nullable=False),
    sa.Column('symbols_json', sa.JSON(), nullable=False),
    sa.Column('initial_cash', sa.Float(), nullable=False),
    sa.Column('start_date', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('account_id')
    )
    with op.batch_alter_table('paper_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_paper_accounts_owner_id'), ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_table('paper_accounts')

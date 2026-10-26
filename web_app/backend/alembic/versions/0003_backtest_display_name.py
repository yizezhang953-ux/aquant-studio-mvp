"""backtest_runs.display_name: a user-editable name for each saved backtest

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26 12:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("backtest_runs")}
    if "display_name" not in columns:
        with op.batch_alter_table('backtest_runs', schema=None) as batch_op:
            batch_op.add_column(sa.Column('display_name', sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('backtest_runs', schema=None) as batch_op:
        batch_op.drop_column('display_name')

"""automation_settings / automation_runs: the daily after-close job and its history

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "automation_settings" not in tables:
        op.create_table('automation_settings',
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('run_time', sa.String(length=5), nullable=False),
        sa.Column('provider_id', sa.String(length=40), nullable=False),
        sa.Column('notify_channel', sa.String(length=20), nullable=False),
        sa.Column('notify_target', sa.String(length=500), nullable=False),
        sa.Column('last_run_date', sa.String(length=10), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('owner_id')
        )
    if "automation_runs" not in tables:
        op.create_table('automation_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('run_date', sa.String(length=10), nullable=False),
        sa.Column('trigger', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('summary_json', sa.JSON(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('notify_status', sa.String(length=20), nullable=False),
        sa.Column('notify_error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('automation_runs', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_automation_runs_owner_id'), ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_table('automation_runs')
    op.drop_table('automation_settings')

"""Add risk diversification fields to agents table.

Phase 6: consecutive_work_turns, days_sick, max_health

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("consecutive_work_turns", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agents", sa.Column("days_sick", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agents", sa.Column("max_health", sa.Float(), nullable=False, server_default="1.0"))


def downgrade() -> None:
    op.drop_column("agents", "max_health")
    op.drop_column("agents", "days_sick")
    op.drop_column("agents", "consecutive_work_turns")

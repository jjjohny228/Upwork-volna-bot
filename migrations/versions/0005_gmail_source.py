"""switch job source to Gmail: add rate/ai_qualified, drop feeds

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("rate", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("ai_qualified", sa.Boolean(), nullable=True))
    # Dropping the column also drops its FK to feeds (Postgres).
    op.drop_column("jobs", "feed_id")
    op.drop_table("feeds")


def downgrade() -> None:
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.add_column(
        "jobs",
        sa.Column("feed_id", sa.Integer, sa.ForeignKey("feeds.id"), nullable=True),
    )
    op.drop_column("jobs", "ai_qualified")
    op.drop_column("jobs", "rate")

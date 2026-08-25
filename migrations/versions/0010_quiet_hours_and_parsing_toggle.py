"""quiet hours + parsing start/pause: per-user scheduling columns

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25

Adds per-user parsing schedule to `users`: `parsing_active` (manual on/off),
`timezone` (IANA name), `quiet_hours_enabled`, and the local-time
`quiet_start`/`quiet_end` window. Defaults keep existing users parsing normally
with quiet hours off, so no backfill is needed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("parsing_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("users", sa.Column("timezone", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("quiet_start", sa.Time(), nullable=True))
    op.add_column("users", sa.Column("quiet_end", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "quiet_end")
    op.drop_column("users", "quiet_start")
    op.drop_column("users", "quiet_hours_enabled")
    op.drop_column("users", "timezone")
    op.drop_column("users", "parsing_active")

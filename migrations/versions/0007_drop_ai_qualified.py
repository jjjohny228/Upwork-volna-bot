"""drop jobs.ai_qualified: qualification now comes only from the local qualifier

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("jobs", "ai_qualified")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("ai_qualified", sa.Boolean(), nullable=True))

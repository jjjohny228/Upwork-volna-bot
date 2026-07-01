"""make jobs.pub_date timezone-aware

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "jobs",
        "pub_date",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(timezone=False),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "jobs",
        "pub_date",
        type_=sa.DateTime(timezone=False),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

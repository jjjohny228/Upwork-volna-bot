"""add resume.pdf_bytes for stored resume file

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resume", sa.Column("pdf_bytes", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("resume", "pdf_bytes")

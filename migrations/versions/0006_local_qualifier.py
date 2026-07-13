"""local qualifier: add jobs.qualified, drop fit_score/skill_gaps

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("qualified", sa.Boolean(), nullable=True))
    op.drop_column("jobs", "fit_score")
    op.drop_column("jobs", "skill_gaps")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("skill_gaps", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("fit_score", sa.Integer(), nullable=True))
    op.drop_column("jobs", "qualified")

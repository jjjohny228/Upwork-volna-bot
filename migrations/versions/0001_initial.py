"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-01
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("feed_id", sa.Integer, sa.ForeignKey("feeds.id"), nullable=False),
        sa.Column("external_pid", sa.Text, nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("upwork_link", sa.Text, nullable=False),
        sa.Column("categories", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("pub_date", sa.DateTime, nullable=True),
        sa.Column("fit_score", sa.Integer, nullable=True),
        sa.Column("fit_reasoning", sa.Text, nullable=True),
        sa.Column("short_summary", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "resume",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "portfolio_projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("link", sa.Text, nullable=True),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "proposal_examples",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("user_feedback", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    # Note: skip ivfflat index on embedding columns for now — MVP will have a
    # handful of rows; add `CREATE INDEX ... USING ivfflat (embedding vector_cosine_ops)`
    # in a later migration once proposal_examples/portfolio_projects grow large.


def downgrade() -> None:
    op.drop_table("proposals")
    op.drop_table("proposal_examples")
    op.drop_table("portfolio_projects")
    op.drop_table("resume")
    op.drop_table("jobs")
    op.drop_table("feeds")

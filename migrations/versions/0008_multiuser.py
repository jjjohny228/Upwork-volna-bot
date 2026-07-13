"""multi-user: users table + per-user ownership of jobs/resume/portfolio/examples

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-12

Creates the `users` table, provisions the admin as the first user (from
ADMIN_TELEGRAM_ID), adds a nullable `user_id` FK to every owned table, backfills
existing rows to the admin, and swaps the global `external_pid` uniqueness for a
per-user `(user_id, external_pid)` dedup key.
"""

import sqlalchemy as sa
from alembic import op

from upwork_bot.config import get_settings

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_OWNED_TABLES = ("jobs", "resume", "portfolio_projects", "proposal_examples")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("gmail_address", sa.Text(), nullable=True),
        sa.Column("gmail_app_password", sa.Text(), nullable=True),
        sa.Column("analysis_prompt", sa.Text(), nullable=True),
        sa.Column("gmail_cursor", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_qualified_only", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # Provision the admin as the first user and backfill all existing rows to them.
    admin_telegram_id = get_settings().admin_telegram_id
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("telegram_id", sa.BigInteger),
        sa.column("display_name", sa.Text),
    )
    op.bulk_insert(
        users,
        [{"telegram_id": admin_telegram_id, "display_name": "admin"}],
    )
    conn = op.get_bind()
    admin_id = conn.execute(
        sa.text("SELECT id FROM users WHERE telegram_id = :tid"),
        {"tid": admin_telegram_id},
    ).scalar_one()

    for table in _OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_user_id",
            table,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        op.execute(sa.text(f"UPDATE {table} SET user_id = {admin_id}"))

    # 0001 created this as a column-level unique, so Postgres auto-named it.
    op.drop_constraint("jobs_external_pid_key", "jobs", type_="unique")
    op.create_unique_constraint("uq_jobs_user_external_pid", "jobs", ["user_id", "external_pid"])


def downgrade() -> None:
    op.drop_constraint("uq_jobs_user_external_pid", "jobs", type_="unique")
    op.create_unique_constraint("jobs_external_pid_key", "jobs", ["external_pid"])

    for table in _OWNED_TABLES:
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")
        op.drop_column(table, "user_id")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

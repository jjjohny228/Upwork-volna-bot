"""full personalization: mailboxes table + per-user rate/signature

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-23

Adds the `mailboxes` table (1 user -> N inboxes) so each user polls their own
Gmail account(s); adds per-user `hourly_rate` and `signature_name` to `users`
(moving them off global Settings); backfills the admin's mailbox + rate/signature
from the old global env settings; and drops the now-redundant single-mailbox
columns (`gmail_address`, `gmail_app_password`, `gmail_cursor`) that 0008 added to
`users` but no UI ever populated.
"""

import sqlalchemy as sa
from alembic import op

from upwork_bot.config import get_settings

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailboxes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("app_password", sa.Text(), nullable=False),
        sa.Column("mailbox", sa.Text(), nullable=False, server_default="INBOX"),
        sa.Column("imap_host", sa.Text(), nullable=False, server_default="imap.gmail.com"),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_mailboxes_user_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "address", name="uq_mailboxes_user_address"),
    )
    op.create_index("ix_mailboxes_user_id", "mailboxes", ["user_id"])

    op.add_column(
        "users",
        sa.Column("hourly_rate", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("signature_name", sa.Text(), nullable=True))

    settings = get_settings()
    conn = op.get_bind()
    admin_id = conn.execute(
        sa.text("SELECT id FROM users WHERE telegram_id = :tid"),
        {"tid": settings.admin_telegram_id},
    ).scalar_one_or_none()

    if admin_id is not None:
        # Backfill the admin's per-user rate/signature from the old global settings.
        conn.execute(
            sa.text("UPDATE users SET hourly_rate = :rate, signature_name = :sig WHERE id = :id"),
            {
                "rate": settings.hourly_rate,
                "sig": settings.proposal_signature_name or None,
                "id": admin_id,
            },
        )
        # Seed the admin's mailbox from the old global Gmail env, if configured.
        if settings.gmail_address and settings.gmail_app_password:
            mailboxes = sa.table(
                "mailboxes",
                sa.column("user_id", sa.Integer),
                sa.column("address", sa.Text),
                sa.column("app_password", sa.Text),
                sa.column("mailbox", sa.Text),
                sa.column("imap_host", sa.Text),
            )
            op.bulk_insert(
                mailboxes,
                [
                    {
                        "user_id": admin_id,
                        "address": settings.gmail_address,
                        "app_password": settings.gmail_app_password,
                        "mailbox": settings.gmail_mailbox,
                        "imap_host": settings.gmail_imap_host,
                    }
                ],
            )

    # Drop the single-mailbox columns 0008 added to users; mailboxes supersedes them.
    op.drop_column("users", "gmail_cursor")
    op.drop_column("users", "gmail_app_password")
    op.drop_column("users", "gmail_address")


def downgrade() -> None:
    op.add_column("users", sa.Column("gmail_address", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("gmail_app_password", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("gmail_cursor", sa.Text(), nullable=True))

    op.drop_column("users", "signature_name")
    op.drop_column("users", "hourly_rate")

    op.drop_index("ix_mailboxes_user_id", table_name="mailboxes")
    op.drop_table("mailboxes")

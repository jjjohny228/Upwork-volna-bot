from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job, Mailbox
from upwork_bot.db.repo import add_mailbox, add_user, delete_user, set_mailbox_cursor
from upwork_bot.gmail.client import JobEmail
from upwork_bot.gmail.poller import poll_once


def _job_email(pid: str) -> JobEmail:
    return JobEmail(
        external_pid=pid,
        title="t",
        description="d",
        upwork_link="https://www.upwork.com/jobs/~2",
        rate="Hourly Rate: 25 - 47 USD",
    )


async def _noop(job: Job) -> None:
    return None


@pytest.mark.asyncio
async def test_poll_once_dedupes_repeated_pid():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=556001, display_name="poller")
        await add_mailbox(session, user.id, address="a@x.com", app_password="p")

    seen: list[int] = []

    async def on_new_job(job: Job) -> None:
        seen.append(job.id)

    # Only our test mailbox yields the email; any ambient mailbox stays empty.
    def fake_fetch(address, *args, **kwargs):
        return [_job_email("poller-dedup-1")] if address == "a@x.com" else []

    try:
        # Two poll cycles return the same email; only the first should be new.
        with patch("upwork_bot.gmail.poller.fetch_new_job_emails", side_effect=fake_fetch):
            first = await poll_once(on_new_job)
            second = await poll_once(on_new_job)

        assert first == 1
        assert second == 0
        assert len(seen) == 1

        async with AsyncSessionLocal() as session:
            rows = list(
                (await session.execute(select(Job).where(Job.user_id == user.id))).scalars()
            )
            assert len(rows) == 1
            # The mailbox cursor advanced so a restart won't re-scan handled mail.
            mb = (
                await session.execute(select(Mailbox).where(Mailbox.user_id == user.id))
            ).scalar_one()
            assert mb.cursor is not None
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=556001)


@pytest.mark.asyncio
async def test_poll_once_ignores_cursor_older_than_startup():
    """A restart resets the effective watermark to startup time, so a stale
    cursor from a previous run never drags the poll back into the backlog."""
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=556004, display_name="restart")
        mb = await add_mailbox(session, user.id, address="a@x.com", app_password="p")
        # Cursor left over from a run 3 days ago.
        stale = datetime.now(tz=UTC) - timedelta(days=3)
        await set_mailbox_cursor(session, mb.id, stale.isoformat())

    startup = datetime.now(tz=UTC)
    seen_since: list[datetime] = []

    def fake_fetch(address, app_password, vollna_sender, mailbox, imap_host, since):
        if address == "a@x.com":
            seen_since.append(since)
        return []

    try:
        with patch("upwork_bot.gmail.poller.fetch_new_job_emails", side_effect=fake_fetch):
            await poll_once(_noop, startup)

        assert seen_since == [startup]
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=556004)


@pytest.mark.asyncio
async def test_poll_once_assigns_jobs_per_mailbox_owner():
    async with AsyncSessionLocal() as session:
        user_a = await add_user(session, telegram_id=556002, display_name="a")
        user_b = await add_user(session, telegram_id=556003, display_name="b")
        await add_mailbox(session, user_a.id, address="a@x.com", app_password="p")
        await add_mailbox(session, user_b.id, address="b@x.com", app_password="p")

    pids = {"a@x.com": "pid-a", "b@x.com": "pid-b"}

    def fake_fetch(address, *args, **kwargs):
        pid = pids.get(address)
        return [_job_email(pid)] if pid else []

    try:
        with patch("upwork_bot.gmail.poller.fetch_new_job_emails", side_effect=fake_fetch):
            count = await poll_once(_noop)

        # Ambient mailboxes (if any) yield nothing, so exactly our two jobs are new.
        assert count == 2
        async with AsyncSessionLocal() as session:
            job_a = (
                await session.execute(select(Job).where(Job.external_pid == "pid-a"))
            ).scalar_one()
            job_b = (
                await session.execute(select(Job).where(Job.external_pid == "pid-b"))
            ).scalar_one()
            assert job_a.user_id == user_a.id
            assert job_b.user_id == user_b.id
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=556002)
            await delete_user(session, telegram_id=556003)

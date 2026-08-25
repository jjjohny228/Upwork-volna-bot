import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from upwork_bot.config import get_settings
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import (
    insert_job_if_new,
    list_active_mailboxes,
    list_users,
    set_mailbox_cursor,
)
from upwork_bot.gmail.client import fetch_new_job_emails
from upwork_bot.gmail.schedule import is_parsing_allowed

logger = logging.getLogger(__name__)

OnNewJob = Callable[[Job], Awaitable[None]]


def _parse_cursor(cursor: str | None, default: datetime) -> datetime:
    if not cursor:
        return default
    try:
        return datetime.fromisoformat(cursor)
    except ValueError:
        return default


async def poll_once(on_new_job: OnNewJob, since: datetime | None = None) -> int:
    """Poll every active mailbox once, dedup + notify new jobs, advance cursors.

    `since` is the fallback watermark for a mailbox that has no persisted cursor
    yet (first poll after startup); a mailbox's own `cursor` takes precedence.
    """
    settings = get_settings()
    fallback = since or datetime.now(tz=UTC)

    async with AsyncSessionLocal() as session:
        mailboxes = await list_active_mailboxes(session)
        owners = {u.id: u for u in await list_users(session)}

    new_count = 0
    for mb in mailboxes:
        poll_start = datetime.now(tz=UTC)
        owner = owners.get(mb.user_id)
        if owner is None or not is_parsing_allowed(owner, poll_start):
            # Parsing suspended for this owner: advance the watermark without
            # fetching so mail that arrived while suspended is later dropped by
            # the `since` cutoff (never parsed, never delivered).
            # Note: the cursor only advances on a suppressed poll, so an email that
            # arrives in the last interval before the window ends can still be
            # delivered on the first allowed poll afterward, bounded by
            # POLL_INTERVAL_SECONDS — expected, not a bug.
            async with AsyncSessionLocal() as session:
                await set_mailbox_cursor(session, mb.id, poll_start.isoformat())
            continue

        # A stale cursor from a previous run never drags the poll below the
        # startup watermark — each restart ignores the accumulated backlog.
        mb_since = max(_parse_cursor(mb.cursor, fallback), fallback)
        try:
            job_emails = await asyncio.to_thread(
                fetch_new_job_emails,
                mb.address,
                mb.app_password,
                settings.vollna_sender,
                mb.mailbox,
                mb.imap_host,
                mb_since,
            )
        except Exception:
            logger.exception("Failed to fetch mailbox %s (%s)", mb.id, mb.address)
            continue

        for job_email in job_emails:
            async with AsyncSessionLocal() as session:
                job = await insert_job_if_new(session, job_email, mb.user_id)
            if job is not None:
                new_count += 1
                await on_new_job(job)

        # Advance the mailbox watermark so restarts don't re-scan handled mail.
        async with AsyncSessionLocal() as session:
            await set_mailbox_cursor(session, mb.id, poll_start.isoformat())

    return new_count


async def run_forever(interval_seconds: int, on_new_job: OnNewJob) -> None:
    # Only react to jobs that arrive after startup; ignore the unread backlog for
    # mailboxes that have no persisted cursor yet.
    since = datetime.now(tz=UTC)
    while True:
        try:
            new_count = await poll_once(on_new_job, since)
            logger.info("Gmail poll cycle complete, %d new jobs", new_count)
        except Exception:
            logger.exception("Poll cycle failed")
        await asyncio.sleep(interval_seconds)

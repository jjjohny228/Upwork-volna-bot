import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from upwork_bot.config import get_settings
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import get_or_create_admin_user, insert_job_if_new
from upwork_bot.gmail.client import fetch_new_job_emails

logger = logging.getLogger(__name__)

OnNewJob = Callable[[Job], Awaitable[None]]


async def poll_once(on_new_job: OnNewJob, since: datetime | None = None) -> int:
    settings = get_settings()
    try:
        job_emails = await asyncio.to_thread(fetch_new_job_emails, settings, since)
    except Exception:
        logger.exception("Failed to fetch Gmail")
        return 0

    # Phase 4 will loop over active users; for now all jobs belong to the admin.
    async with AsyncSessionLocal() as session:
        admin = await get_or_create_admin_user(session, settings.admin_telegram_id)
        admin_id = admin.id

    new_count = 0
    for job_email in job_emails:
        async with AsyncSessionLocal() as session:
            job = await insert_job_if_new(session, job_email, admin_id)
        if job is not None:
            new_count += 1
            await on_new_job(job)

    return new_count


async def run_forever(interval_seconds: int, on_new_job: OnNewJob) -> None:
    # Only react to jobs that arrive after startup; ignore the unread backlog.
    since = datetime.now(tz=UTC)
    while True:
        try:
            new_count = await poll_once(on_new_job, since)
            logger.info("Gmail poll cycle complete, %d new jobs", new_count)
        except Exception:
            logger.exception("Poll cycle failed")
        await asyncio.sleep(interval_seconds)

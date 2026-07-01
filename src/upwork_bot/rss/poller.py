import asyncio
import logging
from collections.abc import Awaitable, Callable

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import get_active_feeds, insert_job_if_new
from upwork_bot.rss.client import fetch_feed

logger = logging.getLogger(__name__)

OnNewJob = Callable[[Job], Awaitable[None]]


async def poll_once(on_new_job: OnNewJob) -> int:
    new_count = 0
    async with AsyncSessionLocal() as session:
        feeds = await get_active_feeds(session)

    for feed in feeds:
        try:
            rss_jobs = await fetch_feed(feed.url)
        except Exception:
            logger.exception("Failed to fetch feed %s", feed.url)
            continue

        for rss_job in rss_jobs:
            async with AsyncSessionLocal() as session:
                job = await insert_job_if_new(session, feed.id, rss_job)
            if job is not None:
                new_count += 1
                await on_new_job(job)

    return new_count


async def run_forever(interval_seconds: int, on_new_job: OnNewJob) -> None:
    while True:
        try:
            new_count = await poll_once(on_new_job)
            logger.info("Poll cycle complete, %d new jobs", new_count)
        except Exception:
            logger.exception("Poll cycle failed")
        await asyncio.sleep(interval_seconds)

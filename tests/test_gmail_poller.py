from unittest.mock import patch

import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.gmail.client import JobEmail
from upwork_bot.gmail.poller import poll_once


@pytest.mark.asyncio
async def test_poll_once_dedupes_repeated_pid():
    job_email = JobEmail(
        external_pid="poller-dedup-1",
        title="t",
        description="d",
        upwork_link="https://www.upwork.com/jobs/~2",
        rate="Hourly Rate: 25 - 47 USD",
    )

    seen: list[int] = []

    async def on_new_job(job: Job) -> None:
        seen.append(job.id)

    # Two poll cycles return the same email; only the first should be new.
    with patch("upwork_bot.gmail.poller.fetch_new_job_emails", return_value=[job_email]):
        first = await poll_once(on_new_job)
        second = await poll_once(on_new_job)

    assert first == 1
    assert second == 0
    assert len(seen) == 1

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Job).where(Job.external_pid == "poller-dedup-1"))
        rows = list(result.scalars())
        assert len(rows) == 1
        await session.delete(rows[0])
        await session.commit()

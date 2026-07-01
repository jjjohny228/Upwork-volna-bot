import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed, Job
from upwork_bot.db.repo import insert_job_if_new
from upwork_bot.rss.client import RssJob


@pytest.mark.asyncio
async def test_insert_job_if_new_dedupes_by_pid():
    async with AsyncSessionLocal() as session:
        feed = Feed(url="https://vollna.com/rss/dedup-test", label="dedup-test")
        session.add(feed)
        await session.commit()

        rss_job = RssJob(
            external_pid="dedup-pid-1",
            title="t",
            description="d",
            upwork_link="https://upwork.com/jobs/~1",
        )

        first = await insert_job_if_new(session, feed.id, rss_job)
        second = await insert_job_if_new(session, feed.id, rss_job)

        assert first is not None
        assert second is None

        result = await session.execute(select(Job).where(Job.external_pid == "dedup-pid-1"))
        rows = list(result.scalars())
        assert len(rows) == 1

        await session.delete(rows[0])
        await session.delete(feed)
        await session.commit()

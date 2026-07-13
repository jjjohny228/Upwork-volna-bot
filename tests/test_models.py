import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job


@pytest.mark.asyncio
async def test_insert_and_query_job():
    async with AsyncSessionLocal() as session:
        job = Job(
            external_pid="model-test-pid-123",
            title="test job",
            description="d",
            upwork_link="https://www.upwork.com/jobs/~1",
            categories=[],
            rate="Hourly Rate: 25 - 47 USD",
        )
        session.add(job)
        await session.commit()

        result = await session.execute(select(Job).where(Job.external_pid == job.external_pid))
        loaded = result.scalar_one()
        assert loaded.title == "test job"
        assert loaded.rate == "Hourly Rate: 25 - 47 USD"

        await session.delete(loaded)
        await session.commit()

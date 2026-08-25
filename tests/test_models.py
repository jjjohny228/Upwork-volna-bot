import datetime as _dt

import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import add_user, delete_user


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


@pytest.mark.asyncio
async def test_user_scheduling_defaults_and_fields():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558100, display_name="sched")
    try:
        # Defaults preserve current behavior: parsing on, quiet off, no tz/window.
        assert user.parsing_active is True
        assert user.quiet_hours_enabled is False
        assert user.timezone is None
        assert user.quiet_start is None
        assert user.quiet_end is None

        async with AsyncSessionLocal() as session:
            reloaded = await session.get(type(user), user.id)
            reloaded.timezone = "Europe/Kyiv"
            reloaded.quiet_start = _dt.time(23, 0)
            reloaded.quiet_end = _dt.time(7, 0)
            reloaded.quiet_hours_enabled = True
            reloaded.parsing_active = False
            await session.commit()

        async with AsyncSessionLocal() as session:
            again = await session.get(type(user), user.id)
            assert again.timezone == "Europe/Kyiv"
            assert again.quiet_start == _dt.time(23, 0)
            assert again.quiet_end == _dt.time(7, 0)
            assert again.quiet_hours_enabled is True
            assert again.parsing_active is False
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558100)

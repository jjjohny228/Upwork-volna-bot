from unittest.mock import AsyncMock

import pytest

from upwork_bot.bot.handlers.jobs import notify_new_job
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import add_user, delete_user, set_notify_qualified_only


def _job(user_id: int, qualified: bool) -> Job:
    return Job(
        id=1,
        user_id=user_id,
        external_pid="notify-pid",
        title="Some job",
        description="d",
        upwork_link="https://www.upwork.com/jobs/~7",
        rate="Hourly Rate: 10 - 20 USD",
        qualified=qualified,
    )


@pytest.mark.asyncio
async def test_qualified_only_user_skips_disqualified_job():
    tid = 555_000_333
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=tid, display_name="q")
        await set_notify_qualified_only(session, tid, True)
        user_id = user.id
    try:
        bot = AsyncMock()
        await notify_new_job(bot, _job(user_id, qualified=False))
        bot.send_message.assert_not_awaited()

        await notify_new_job(bot, _job(user_id, qualified=True))
        bot.send_message.assert_awaited_once()
        assert bot.send_message.await_args.kwargs["chat_id"] == tid
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, tid)


@pytest.mark.asyncio
async def test_all_jobs_user_receives_disqualified_job():
    tid = 555_000_444
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=tid, display_name="a")
        user_id = user.id  # default notify_qualified_only=False
    try:
        bot = AsyncMock()
        await notify_new_job(bot, _job(user_id, qualified=False))
        bot.send_message.assert_awaited_once()
        kwargs = bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == tid
        assert kwargs["disable_notification"] is True  # disqualified → silent
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, tid)

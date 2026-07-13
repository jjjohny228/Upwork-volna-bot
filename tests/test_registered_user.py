from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.middlewares.registered_user import RegisteredUserMiddleware
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user, set_active

ADMIN_ID = 617073201


def _make_message(user_id: int) -> Message:
    msg = Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=user_id, type="private"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="x"),
    )
    # answer() would hit the Telegram API; stub it for rejection paths.
    object.__setattr__(msg, "answer", AsyncMock())
    return msg


@pytest.mark.asyncio
async def test_admin_is_auto_provisioned_and_injected():
    middleware = RegisteredUserMiddleware(admin_telegram_id=ADMIN_ID)
    handler = AsyncMock(return_value="ok")
    data: dict = {}

    result = await middleware(handler, _make_message(ADMIN_ID), data)

    assert result == "ok"
    handler.assert_awaited_once()
    assert data["user"].telegram_id == ADMIN_ID


@pytest.mark.asyncio
async def test_unknown_user_blocked():
    middleware = RegisteredUserMiddleware(admin_telegram_id=ADMIN_ID)
    handler = AsyncMock(return_value="ok")

    result = await middleware(handler, _make_message(123_456_789), {})

    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_registered_user_passes():
    tid = 555_000_111
    async with AsyncSessionLocal() as session:
        await add_user(session, telegram_id=tid, display_name="reg")
    try:
        middleware = RegisteredUserMiddleware(admin_telegram_id=ADMIN_ID)
        handler = AsyncMock(return_value="ok")
        data: dict = {}

        result = await middleware(handler, _make_message(tid), data)

        assert result == "ok"
        assert data["user"].telegram_id == tid
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, tid)


@pytest.mark.asyncio
async def test_inactive_user_blocked():
    tid = 555_000_222
    async with AsyncSessionLocal() as session:
        await add_user(session, telegram_id=tid, display_name="reg")
        await set_active(session, tid, False)
    try:
        middleware = RegisteredUserMiddleware(admin_telegram_id=ADMIN_ID)
        handler = AsyncMock(return_value="ok")

        result = await middleware(handler, _make_message(tid), {})

        assert result is None
        handler.assert_not_awaited()
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, tid)

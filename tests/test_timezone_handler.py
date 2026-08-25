from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.handlers.timezone import process_manual_timezone
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user, get_user_by_telegram_id


def _msg(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=TgUser(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_manual_timezone_valid_saves_and_clears():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558400, display_name="tz")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_manual_timezone(_msg("Europe/Kyiv"), state, user)
        state.clear.assert_awaited()
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558400)).timezone == "Europe/Kyiv"
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558400)


@pytest.mark.asyncio
async def test_manual_timezone_invalid_rejected():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558401, display_name="tz2")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_manual_timezone(_msg("Not/AZone"), state, user)
        # Invalid name -> stays in state, nothing saved.
        state.clear.assert_not_awaited()
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558401)).timezone is None
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558401)

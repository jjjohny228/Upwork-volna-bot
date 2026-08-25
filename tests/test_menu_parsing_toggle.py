from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.handlers.menu import pause_parsing, start_parsing
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user, get_user_by_telegram_id


def _make_message() -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=TgUser(id=42, is_bot=False, first_name="owner"),
        text="⏸ Pause parsing",
    )


@pytest.mark.asyncio
async def test_pause_then_start_parsing():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558300, display_name="toggle")

    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await pause_parsing(_make_message(), state, user)
        assert user.parsing_active is False
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558300)).parsing_active is False

        with patch.object(Message, "answer", new_callable=AsyncMock):
            await start_parsing(_make_message(), state, user)
        assert user.parsing_active is True
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558300)).parsing_active is True
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558300)

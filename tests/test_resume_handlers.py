from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User

from upwork_bot.bot.handlers.resume import process_resume_content, start_set_resume
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import get_active_resume


def _make_state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=42, user_id=42))


def _make_message(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_set_resume_via_text():
    state = _make_state()

    with patch.object(Message, "answer", new_callable=AsyncMock):
        await start_set_resume(_make_message("✏️ Set resume"), state)
        await process_resume_content(_make_message("Menu-test resume content"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        content = await get_active_resume(session)
        assert content == "Menu-test resume content"

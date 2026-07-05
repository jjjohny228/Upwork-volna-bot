from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from sqlalchemy import select

from upwork_bot.bot.handlers.proposal_examples import process_example_text, start_add_example
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import ProposalExample


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
async def test_add_example_happy_path():
    state = _make_state()
    fake_embedding = [0.0] * 1536

    with (
        patch.object(Message, "answer", new_callable=AsyncMock),
        patch(
            "upwork_bot.bot.handlers.proposal_examples.embed_text",
            new=AsyncMock(return_value=fake_embedding),
        ),
    ):
        await start_add_example(_make_message("➕ Add example"), state)
        await process_example_text(_make_message("menu-test example text"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ProposalExample).where(ProposalExample.source_text == "menu-test example text")
        )
        example = result.scalar_one()

        await session.delete(example)
        await session.commit()

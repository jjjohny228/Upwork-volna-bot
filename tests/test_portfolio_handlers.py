from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from sqlalchemy import select

from upwork_bot.bot.handlers.portfolio import (
    process_project_description,
    process_project_link,
    start_add_project,
)
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import PortfolioProject


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
async def test_add_project_with_link():
    state = _make_state()

    fake_embedding = [0.0] * 1536
    with (
        patch.object(Message, "answer", new_callable=AsyncMock),
        patch(
            "upwork_bot.bot.handlers.portfolio.embed_text",
            new=AsyncMock(return_value=fake_embedding),
        ),
    ):
        await start_add_project(_make_message("➕ Add project"), state)
        await process_project_description(_make_message("menu-test-description"), state)
        # process_project_description expects title already stored; set it directly since
        # this test only exercises the description->link->save leg of the sequence.
        await state.update_data(title="menu-test-title")
        await process_project_description(_make_message("menu-test-description"), state)
        await process_project_link(_make_message("https://example.com/menu-test"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PortfolioProject).where(PortfolioProject.title == "menu-test-title")
        )
        project = result.scalar_one()
        assert project.description == "menu-test-description"
        assert project.link == "https://example.com/menu-test"

        await session.delete(project)
        await session.commit()

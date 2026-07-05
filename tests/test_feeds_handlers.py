from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from sqlalchemy import select

from upwork_bot.bot.handlers.feeds import process_feed_label, process_feed_url, start_add_feed
from upwork_bot.bot.states import FeedStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed


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
async def test_add_feed_happy_path():
    state = _make_state()

    with patch.object(Message, "answer", new_callable=AsyncMock):
        await start_add_feed(_make_message("➕ Add feed"), state)
        assert await state.get_state() == FeedStates.waiting_for_url.state

        await process_feed_url(_make_message("https://vollna.com/rss/menu-test"), state)
        assert await state.get_state() == FeedStates.waiting_for_label.state
        data = await state.get_data()
        assert data["url"] == "https://vollna.com/rss/menu-test"

        await process_feed_label(_make_message("menu-test-label"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Feed).where(Feed.url == "https://vollna.com/rss/menu-test")
        )
        feed = result.scalar_one()
        assert feed.label == "menu-test-label"

        await session.delete(feed)
        await session.commit()


@pytest.mark.asyncio
async def test_add_feed_cancel_does_not_save():
    state = _make_state()

    with patch.object(Message, "answer", new_callable=AsyncMock):
        await start_add_feed(_make_message("➕ Add feed"), state)
        await process_feed_url(_make_message("❌ Cancel"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Feed).where(Feed.label == "menu-test-label"))
        assert result.scalar_one_or_none() is None

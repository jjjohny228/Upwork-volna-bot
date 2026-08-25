import datetime as _dt
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.handlers.quiet_hours import (
    process_end,
    process_start,
    toggle_quiet_hours,
)
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user, get_user_by_telegram_id, set_timezone


def _msg(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=TgUser(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_enable_blocked_without_timezone():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558500, display_name="qh")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await toggle_quiet_hours(_msg("🔔 Enable quiet hours"), state, user)
        # No tz -> refuse to enable.
        assert user.quiet_hours_enabled is False
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558500)).quiet_hours_enabled is False
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558500)


@pytest.mark.asyncio
async def test_enable_with_timezone_succeeds():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558501, display_name="qh2")
        await set_timezone(session, 558501, "UTC")
        user.timezone = "UTC"
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await toggle_quiet_hours(_msg("🔔 Enable quiet hours"), state, user)
        assert user.quiet_hours_enabled is True
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558501)).quiet_hours_enabled is True
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558501)


@pytest.mark.asyncio
async def test_set_window_valid_two_steps():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558502, display_name="qh3")
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"quiet_start": "23:00"})
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_start(_msg("23:00"), state, user)
            state.update_data.assert_awaited_with(quiet_start="23:00")
            await process_end(_msg("07:00"), state, user)
        async with AsyncSessionLocal() as session:
            saved = await get_user_by_telegram_id(session, 558502)
            assert saved.quiet_start == _dt.time(23, 0)
            assert saved.quiet_end == _dt.time(7, 0)
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558502)


@pytest.mark.asyncio
async def test_set_window_rejects_bad_start():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558503, display_name="qh4")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_start(_msg("25:99"), state, user)
        # Bad time -> stays waiting, no data stored.
        state.update_data.assert_not_awaited()
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558503)

from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.middlewares.admin_only import AdminOnlyMiddleware


def _make_message(user_id: int) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=user_id, type="private"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="x"),
    )


@pytest.mark.asyncio
async def test_admin_passes():
    middleware = AdminOnlyMiddleware(admin_telegram_id=42)
    handler = AsyncMock(return_value="ok")

    result = await middleware(handler, _make_message(42), {})

    handler.assert_awaited_once()
    assert result == "ok"


@pytest.mark.asyncio
async def test_non_admin_blocked():
    middleware = AdminOnlyMiddleware(admin_telegram_id=42)
    handler = AsyncMock(return_value="ok")

    result = await middleware(handler, _make_message(999), {})

    handler.assert_not_awaited()
    assert result is None

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import get_or_create_admin_user, get_user_by_telegram_id

_REJECT_TEXT = "You're not registered for this bot. Ask the admin to add you."


class RegisteredUserMiddleware(BaseMiddleware):
    """Gate every handler on a registered, active `users` row.

    The admin (``admin_telegram_id``) is auto-provisioned on first contact.
    Everyone else must have been added by the admin and stay active. The
    resolved ``User`` is injected into handler ``data["user"]``.
    """

    def __init__(self, admin_telegram_id: int) -> None:
        self.admin_telegram_id = admin_telegram_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user") or getattr(event, "from_user", None)
        if tg_user is None:
            return None

        async with AsyncSessionLocal() as session:
            if tg_user.id == self.admin_telegram_id:
                user = await get_or_create_admin_user(session, self.admin_telegram_id)
            else:
                user = await get_user_by_telegram_id(session, tg_user.id)

        if user is None or not user.is_active:
            await self._reject(event)
            return None

        data["user"] = user
        return await handler(event, data)

    @staticmethod
    async def _reject(event: TelegramObject) -> None:
        if isinstance(event, Message):
            await event.answer(_REJECT_TEXT)
        elif isinstance(event, CallbackQuery):
            await event.answer(_REJECT_TEXT, show_alert=True)

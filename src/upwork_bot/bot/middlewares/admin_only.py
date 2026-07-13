from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class AdminOnlyMiddleware(BaseMiddleware):
    """Restrict a router to the single admin (``ADMIN_TELEGRAM_ID``).

    Attach to admin-panel routers only; ordinary handlers use
    ``RegisteredUserMiddleware`` instead.
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
        if tg_user is None or tg_user.id != self.admin_telegram_id:
            return None
        return await handler(event, data)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from upwork_bot.bot.handlers import feeds
from upwork_bot.bot.middlewares.owner_only import OwnerOnlyMiddleware
from upwork_bot.config import get_settings


def create_dispatcher() -> Dispatcher:
    settings = get_settings()
    dispatcher = Dispatcher()

    owner_only = OwnerOnlyMiddleware(admin_telegram_id=settings.admin_telegram_id)
    dispatcher.message.middleware(owner_only)
    dispatcher.callback_query.middleware(owner_only)

    dispatcher.include_router(feeds.router)

    return dispatcher


def create_bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

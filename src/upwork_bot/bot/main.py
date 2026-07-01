from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from upwork_bot.bot.handlers import (
    feeds,
    jobs,
    portfolio,
    proposal_examples,
    proposals,
    resume,
)
from upwork_bot.bot.middlewares.owner_only import OwnerOnlyMiddleware
from upwork_bot.config import get_settings


def create_dispatcher() -> Dispatcher:
    settings = get_settings()
    dispatcher = Dispatcher(storage=MemoryStorage())

    owner_only = OwnerOnlyMiddleware(admin_telegram_id=settings.admin_telegram_id)
    dispatcher.message.middleware(owner_only)
    dispatcher.callback_query.middleware(owner_only)

    dispatcher.include_router(feeds.router)
    dispatcher.include_router(resume.router)
    dispatcher.include_router(portfolio.router)
    dispatcher.include_router(proposal_examples.router)
    dispatcher.include_router(jobs.router)
    dispatcher.include_router(proposals.router)

    return dispatcher


def create_bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

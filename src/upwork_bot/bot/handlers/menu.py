from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_DELIVERY_ALL,
    BTN_DELIVERY_QUALIFIED,
    BTN_EXAMPLES,
    BTN_PAUSE_PARSING,
    BTN_PORTFOLIO,
    BTN_RESUME,
    BTN_SETTINGS,
    BTN_START_PARSING,
    examples_menu_kb,
    main_menu_kb,
    portfolio_menu_kb,
    resume_menu_kb,
    settings_menu_kb,
)
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import set_notify_qualified_only, set_parsing_active

router = Router(name="menu")


def _delivery_status_line(notify_qualified_only: bool) -> str:
    mode = "only qualified jobs" if notify_qualified_only else "all jobs"
    return f"Job delivery: <b>{mode}</b>. Pick a mode:"


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer(
        "Welcome to the Upwork Job-Hunter admin menu. Choose a section:",
        reply_markup=main_menu_kb(user.parsing_active),
    )


@router.message(lambda m: m.text == BTN_RESUME)
async def open_resume_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Resume:", reply_markup=resume_menu_kb())


@router.message(lambda m: m.text == BTN_PORTFOLIO)
async def open_portfolio_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Portfolio:", reply_markup=portfolio_menu_kb())


@router.message(lambda m: m.text == BTN_EXAMPLES)
async def open_examples_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Proposal examples:", reply_markup=examples_menu_kb())


@router.message(lambda m: m.text == BTN_SETTINGS)
async def open_settings_menu(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer(
        _delivery_status_line(user.notify_qualified_only),
        reply_markup=settings_menu_kb(user.notify_qualified_only),
    )


@router.message(lambda m: m.text and m.text.startswith(BTN_DELIVERY_ALL))
async def set_delivery_all(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        await set_notify_qualified_only(session, user.telegram_id, False)
    user.notify_qualified_only = False
    await message.answer(
        "✅ You'll now receive <b>all jobs</b> (disqualified ones arrive silently).",
        reply_markup=settings_menu_kb(False),
    )


@router.message(lambda m: m.text and m.text.startswith(BTN_DELIVERY_QUALIFIED))
async def set_delivery_qualified(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        await set_notify_qualified_only(session, user.telegram_id, True)
    user.notify_qualified_only = True
    await message.answer(
        "✅ You'll now receive <b>only qualified jobs</b>.",
        reply_markup=settings_menu_kb(True),
    )


@router.message(lambda m: m.text == BTN_BACK)
async def go_back_to_main_menu(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb(user.parsing_active))


@router.message(lambda m: m.text == BTN_PAUSE_PARSING)
async def pause_parsing(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        await set_parsing_active(session, user.telegram_id, False)
    user.parsing_active = False
    await message.answer(
        "⏸ Parsing <b>paused</b>. Jobs that arrive while paused are skipped.",
        reply_markup=main_menu_kb(user.parsing_active),
    )


@router.message(lambda m: m.text == BTN_START_PARSING)
async def start_parsing(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        await set_parsing_active(session, user.telegram_id, True)
    user.parsing_active = True
    await message.answer(
        "▶️ Parsing <b>started</b>.",
        reply_markup=main_menu_kb(user.parsing_active),
    )

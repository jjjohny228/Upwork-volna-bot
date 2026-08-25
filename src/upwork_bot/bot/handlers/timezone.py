from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_TIMEZONE,
    cancel_kb,
    settings_menu_kb,
    timezone_inline_kb,
)
from upwork_bot.bot.states import TimezoneStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import set_timezone

router = Router(name="timezone")


def _is_valid_tz(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


@router.message(lambda m: m.text == BTN_TIMEZONE)
async def open_timezone(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    current = user.timezone or "not set"
    await message.answer(
        f"Current timezone: <b>{current}</b>.\nPick one or enter it manually:",
        reply_markup=timezone_inline_kb(),
    )


@router.callback_query(F.data.startswith("tz:"))
async def pick_timezone(callback: CallbackQuery, user: User) -> None:
    name = callback.data.split(":", 1)[1]
    if not _is_valid_tz(name):
        await callback.answer("Invalid timezone.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        await set_timezone(session, user.telegram_id, name)
    user.timezone = name
    await callback.message.answer(
        f"✅ Timezone set to <b>{name}</b>.",
        reply_markup=settings_menu_kb(user.notify_qualified_only),
    )
    await callback.answer()


@router.callback_query(F.data == "tz_manual")
async def ask_manual_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TimezoneStates.waiting_for_manual)
    await callback.message.answer(
        "Send an IANA timezone name, e.g. <code>Europe/Kyiv</code>.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(TimezoneStates.waiting_for_manual)
async def process_manual_timezone(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=settings_menu_kb(user.notify_qualified_only)
        )
        return

    name = (message.text or "").strip()
    if not _is_valid_tz(name):
        await message.answer("Unknown timezone. Send an IANA name like Europe/Kyiv.")
        return

    async with AsyncSessionLocal() as session:
        await set_timezone(session, user.telegram_id, name)
    user.timezone = name
    await state.clear()
    await message.answer(
        f"✅ Timezone set to <b>{name}</b>.",
        reply_markup=settings_menu_kb(user.notify_qualified_only),
    )

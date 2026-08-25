from datetime import datetime, time

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_QUIET_HOURS,
    BTN_QUIET_SET_WINDOW,
    BTN_QUIET_TOGGLE_OFF,
    BTN_QUIET_TOGGLE_ON,
    cancel_kb,
    quiet_hours_menu_kb,
)
from upwork_bot.bot.states import QuietHoursStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import set_quiet_hours_enabled, set_quiet_window

router = Router(name="quiet_hours")


def _parse_hhmm(text: str | None) -> time | None:
    try:
        parsed = datetime.strptime((text or "").strip(), "%H:%M")
    except ValueError:
        return None
    return parsed.time()


def _status(user: User) -> str:
    state = "on" if user.quiet_hours_enabled else "off"
    tz = user.timezone or "not set"
    if user.quiet_start and user.quiet_end:
        window = f"{user.quiet_start.strftime('%H:%M')}–{user.quiet_end.strftime('%H:%M')}"
    else:
        window = "not set"
    return (
        f"<b>Quiet hours</b>: {state}\nWindow (local): {window}\nTimezone: {tz}\n\n"
        "During quiet hours parsing is suspended and jobs that arrive are skipped."
    )


@router.message(lambda m: m.text == BTN_QUIET_HOURS)
async def open_quiet_hours(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer(_status(user), reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled))


@router.message(lambda m: m.text in (BTN_QUIET_TOGGLE_ON, BTN_QUIET_TOGGLE_OFF))
async def toggle_quiet_hours(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    enabling = message.text == BTN_QUIET_TOGGLE_ON
    if enabling and not user.timezone:
        await message.answer(
            "Set your 🕒 Timezone first — quiet hours need it.",
            reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled),
        )
        return
    async with AsyncSessionLocal() as session:
        await set_quiet_hours_enabled(session, user.telegram_id, enabling)
    user.quiet_hours_enabled = enabling
    await message.answer(_status(user), reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled))


@router.message(lambda m: m.text == BTN_QUIET_SET_WINDOW)
async def start_set_window(message: Message, state: FSMContext, user: User) -> None:
    await state.set_state(QuietHoursStates.waiting_for_start)
    await message.answer(
        "Send the quiet-hours <b>start</b> time as HH:MM (24h), e.g. 23:00.",
        reply_markup=cancel_kb(),
    )


@router.message(QuietHoursStates.waiting_for_start)
async def process_start(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled)
        )
        return
    if _parse_hhmm(message.text) is None:
        await message.answer("Send a time as HH:MM, e.g. 23:00.")
        return
    await state.update_data(quiet_start=message.text.strip())
    await state.set_state(QuietHoursStates.waiting_for_end)
    await message.answer("Now send the <b>end</b> time as HH:MM, e.g. 07:00.")


@router.message(QuietHoursStates.waiting_for_end)
async def process_end(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled)
        )
        return
    end = _parse_hhmm(message.text)
    if end is None:
        await message.answer("Send a time as HH:MM, e.g. 07:00.")
        return
    data = await state.get_data()
    start = _parse_hhmm(data.get("quiet_start"))
    if start is None or start == end:
        await state.clear()
        await message.answer(
            "Start and end can't be equal — start over with 🕐 Set window.",
            reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled),
        )
        return
    async with AsyncSessionLocal() as session:
        await set_quiet_window(session, user.telegram_id, start, end)
    user.quiet_start, user.quiet_end = start, end
    await state.clear()
    await message.answer(
        f"✅ Quiet hours window set to {start.strftime('%H:%M')}–{end.strftime('%H:%M')}.",
        reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled),
    )

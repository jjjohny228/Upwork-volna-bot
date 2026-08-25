from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_HOURLY_RATE,
    BTN_SIGNATURE,
    cancel_kb,
    settings_menu_kb,
)
from upwork_bot.bot.states import RateStates, SignatureStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import set_hourly_rate, set_signature_name

router = Router(name="user_settings")


@router.message(lambda m: m.text == BTN_HOURLY_RATE)
async def start_set_rate(message: Message, state: FSMContext, user: User) -> None:
    await state.set_state(RateStates.waiting_for_rate)
    current = f"{user.hourly_rate:g}" if user.hourly_rate else "not set"
    await message.answer(
        f"Current hourly rate: {current} USD/h.\nSend a new rate (a number).",
        reply_markup=cancel_kb(),
    )


@router.message(RateStates.waiting_for_rate)
async def process_rate(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=settings_menu_kb(user.notify_qualified_only)
        )
        return

    try:
        rate = float((message.text or "").replace(",", ".").strip())
    except ValueError:
        await message.answer("Send a number, e.g. 45 or 45.5.")
        return

    async with AsyncSessionLocal() as session:
        await set_hourly_rate(session, user.telegram_id, rate)
    user.hourly_rate = rate
    await state.clear()
    await message.answer(
        f"Hourly rate set to {rate:g} USD/h.",
        reply_markup=settings_menu_kb(user.notify_qualified_only),
    )


@router.message(lambda m: m.text == BTN_SIGNATURE)
async def start_set_signature(message: Message, state: FSMContext, user: User) -> None:
    await state.set_state(SignatureStates.waiting_for_signature)
    current = user.signature_name or "not set"
    await message.answer(
        f"Current signature name: {current}.\nSend the name to sign proposals with.",
        reply_markup=cancel_kb(),
    )


@router.message(SignatureStates.waiting_for_signature)
async def process_signature(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=settings_menu_kb(user.notify_qualified_only)
        )
        return

    if not message.text:
        await message.answer("Send the signature name as text.")
        return

    name = message.text.strip()
    async with AsyncSessionLocal() as session:
        await set_signature_name(session, user.telegram_id, name)
    user.signature_name = name
    await state.clear()
    await message.answer(
        f"Signature name set to {name}.",
        reply_markup=settings_menu_kb(user.notify_qualified_only),
    )

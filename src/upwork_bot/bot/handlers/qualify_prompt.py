from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_GEN_PROMPT,
    BTN_QUALIFY_PROMPT,
    BTN_SET_PROMPT,
    BTN_VIEW_PROMPT,
    cancel_kb,
    qualify_prompt_menu_kb,
    regenerate_prompt_kb,
)
from upwork_bot.bot.states import QualifyPromptStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import (
    get_active_resume,
    list_portfolio_projects,
    set_analysis_prompt,
)
from upwork_bot.llm.prompt_gen_chain import generate_analysis_prompt
from upwork_bot.llm.proposal_chain import portfolio_snippet

router = Router(name="qualify_prompt")

_MISSING_MSG = (
    "Can't generate a qualify prompt yet.\n\n"
    "First add:\n"
    "{resume_line}\n"
    "{portfolio_line}\n\n"
    "Then come back and tap ✨ Generate prompt."
)


async def _send_long(message: Message, text: str, reply_markup=None) -> None:
    """Send text in Telegram-safe chunks; attach the keyboard to the last chunk."""
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)] or [""]
    for chunk in chunks[:-1]:
        await message.answer(chunk, parse_mode=None)
    await message.answer(chunks[-1], reply_markup=reply_markup, parse_mode=None)


@router.message(lambda m: m.text == BTN_QUALIFY_PROMPT)
async def open_qualify_prompt_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Qualify prompt — the instructions that decide if a job fits you.",
        reply_markup=qualify_prompt_menu_kb(),
    )


@router.message(lambda m: m.text == BTN_VIEW_PROMPT)
async def view_prompt(message: Message, user: User) -> None:
    if not user.analysis_prompt:
        await message.answer("No custom prompt set — the built-in default is used.")
        return
    await _send_long(message, user.analysis_prompt)


async def _generate_and_save(message: Message, user: User) -> None:
    async with AsyncSessionLocal() as session:
        resume_text = await get_active_resume(session, user.id)
        projects = await list_portfolio_projects(session, user.id)

    if not resume_text or not projects:
        resume_line = "• a resume (📄 Resume)" if not resume_text else "• ✅ resume"
        portfolio_line = (
            "• at least one portfolio project (💼 Portfolio)" if not projects else "• ✅ portfolio"
        )
        await message.answer(
            _MISSING_MSG.format(resume_line=resume_line, portfolio_line=portfolio_line),
            reply_markup=qualify_prompt_menu_kb(),
        )
        return

    await message.answer("Generating your qualify prompt...")
    prompt = await generate_analysis_prompt(resume_text, [portfolio_snippet(p) for p in projects])
    async with AsyncSessionLocal() as session:
        await set_analysis_prompt(session, user.telegram_id, prompt)
    user.analysis_prompt = prompt

    await message.answer("✅ Saved as your qualify prompt:")
    await _send_long(message, prompt, reply_markup=regenerate_prompt_kb())


@router.message(lambda m: m.text == BTN_GEN_PROMPT)
async def generate_prompt(message: Message, user: User) -> None:
    await _generate_and_save(message, user)


@router.callback_query(lambda c: c.data == "regen_qualify_prompt")
async def regenerate_prompt(callback: CallbackQuery, user: User) -> None:
    await callback.answer("Regenerating...")
    await _generate_and_save(callback.message, user)


@router.message(lambda m: m.text == BTN_SET_PROMPT)
async def start_set_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(QualifyPromptStates.waiting_for_prompt)
    await message.answer("Send the qualify prompt text.", reply_markup=cancel_kb())


@router.message(QualifyPromptStates.waiting_for_prompt)
async def process_set_prompt(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=qualify_prompt_menu_kb())
        return

    if not message.text:
        await message.answer("Send the prompt as text.")
        return

    async with AsyncSessionLocal() as session:
        await set_analysis_prompt(session, user.telegram_id, message.text)
    user.analysis_prompt = message.text
    await state.clear()
    await message.answer("Qualify prompt updated.", reply_markup=qualify_prompt_menu_kb())

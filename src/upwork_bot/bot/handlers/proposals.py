from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_WRITE_PROPOSAL,
    cancel_kb,
    main_menu_kb,
)
from upwork_bot.bot.states import CustomProposalStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import (
    get_active_resume,
    get_job,
    get_latest_proposal,
    save_proposal,
    search_similar_examples,
    search_similar_portfolio,
)
from upwork_bot.llm.embeddings import embed_text
from upwork_bot.llm.proposal_chain import generate_proposal, portfolio_snippet

router = Router(name="proposals")


class ProposalFeedbackStates(StatesGroup):
    waiting_for_feedback = State()


def _regenerate_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Regenerate with edits",
                    callback_data=f"regen_proposal:{job_id}",
                )
            ]
        ]
    )


def _custom_regenerate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Regenerate with edits",
                    callback_data="regen_custom",
                )
            ]
        ]
    )


async def _proposal_from_description(
    description: str,
    previous_version: str | None = None,
    feedback: str | None = None,
) -> str:
    """Run the RAG pipeline + LLM for an ad-hoc project description (no stored Job)."""
    title = description.splitlines()[0][:120] if description.strip() else "Custom project"
    async with AsyncSessionLocal() as session:
        resume_text = await get_active_resume(session) or ""
        embedding = await embed_text(description)
        portfolio = await search_similar_portfolio(session, embedding)
        examples = await search_similar_examples(session, embedding)
        portfolio_snippets = [portfolio_snippet(p) for p in portfolio]
        example_snippets = [e.source_text for e in examples]

    return await generate_proposal(
        resume_text=resume_text,
        job_title=title,
        job_description=description,
        portfolio_snippets=portfolio_snippets,
        example_snippets=example_snippets,
        previous_version=previous_version,
        feedback=feedback,
    )


@router.callback_query(lambda c: c.data.startswith("regen_proposal:"))
async def handle_regen_request(callback: CallbackQuery, state: FSMContext) -> None:
    job_id = int(callback.data.split(":", 1)[1])
    await state.set_state(ProposalFeedbackStates.waiting_for_feedback)
    await state.update_data(job_id=job_id)
    await callback.answer()
    await callback.message.answer(
        "Send your corrections as a message and I'll regenerate the draft."
    )


@router.message(ProposalFeedbackStates.waiting_for_feedback)
async def handle_feedback_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    job_id = data["job_id"]
    feedback = message.text or ""

    async with AsyncSessionLocal() as session:
        job = await get_job(session, job_id)
        latest = await get_latest_proposal(session, job_id)
        resume_text = await get_active_resume(session) or ""
        embedding = await embed_text(job.description)
        portfolio = await search_similar_portfolio(session, embedding)
        examples = await search_similar_examples(session, embedding)

        content = await generate_proposal(
            resume_text=resume_text,
            job_title=job.title,
            job_description=job.description,
            portfolio_snippets=[portfolio_snippet(p) for p in portfolio],
            example_snippets=[e.source_text for e in examples],
            previous_version=latest.content if latest else None,
            feedback=feedback,
        )

        next_version = (latest.version + 1) if latest else 1
        await save_proposal(
            session,
            job_id=job_id,
            version=next_version,
            content=content,
            user_feedback=feedback,
        )

    await state.clear()
    await message.reply(content, reply_markup=_regenerate_keyboard(job_id), parse_mode=None)


@router.message(lambda m: m.text == BTN_WRITE_PROPOSAL)
async def start_custom_proposal(message: Message, state: FSMContext) -> None:
    await state.set_state(CustomProposalStates.waiting_for_description)
    await message.answer(
        "Send the project description and I'll write a proposal for it.",
        reply_markup=cancel_kb(),
    )


@router.message(CustomProposalStates.waiting_for_description)
async def write_custom_proposal(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=main_menu_kb())
        return

    description = message.text
    if not description:
        await message.answer("Send the project description as text.")
        return

    # Restore the main menu now so no stray Cancel button lingers after generation.
    await message.answer("Writing proposal...", reply_markup=main_menu_kb())
    content = await _proposal_from_description(description)

    # Keep the description + draft in FSM so the inline "regenerate" can reuse them.
    await state.set_state(None)
    await state.update_data(custom_description=description, custom_draft=content)
    await message.reply(content, reply_markup=_custom_regenerate_keyboard(), parse_mode=None)


@router.callback_query(lambda c: c.data == "regen_custom")
async def handle_custom_regen_request(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await callback.answer()
    if not data.get("custom_description"):
        await callback.message.answer(
            "This draft expired. Tap 🖊 Write proposal to start again.",
            reply_markup=main_menu_kb(),
        )
        return
    await state.set_state(CustomProposalStates.waiting_for_feedback)
    await callback.message.answer(
        "Send your corrections as a message and I'll regenerate the draft."
    )


@router.message(CustomProposalStates.waiting_for_feedback)
async def handle_custom_feedback(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.set_state(None)
        await message.answer("Kept the current draft.", reply_markup=main_menu_kb())
        return

    data = await state.get_data()
    description = data.get("custom_description")
    if not description:
        await state.clear()
        await message.answer(
            "This draft expired. Tap 🖊 Write proposal to start again.",
            reply_markup=main_menu_kb(),
        )
        return

    feedback = message.text or ""
    await message.answer("Regenerating...")
    content = await _proposal_from_description(
        description, previous_version=data.get("custom_draft"), feedback=feedback
    )

    await state.set_state(None)
    await state.update_data(custom_description=description, custom_draft=content)
    await message.reply(content, reply_markup=_custom_regenerate_keyboard(), parse_mode=None)

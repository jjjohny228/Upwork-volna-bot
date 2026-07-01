from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

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
from upwork_bot.llm.proposal_chain import generate_proposal

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
            portfolio_snippets=[f"{p.title}: {p.description}" for p in portfolio],
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
    await message.answer(content, reply_markup=_regenerate_keyboard(job_id))

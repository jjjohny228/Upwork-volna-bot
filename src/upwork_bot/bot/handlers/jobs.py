from aiogram import Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from upwork_bot.config import get_settings
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import (
    get_active_resume,
    get_job,
    save_proposal,
    search_similar_examples,
    search_similar_portfolio,
)
from upwork_bot.llm.embeddings import embed_text
from upwork_bot.llm.proposal_chain import generate_proposal

router = Router(name="jobs")


def _job_keyboard(job_id: int, upwork_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Generate proposal", callback_data=f"gen_proposal:{job_id}"
                ),
                InlineKeyboardButton(text="🔗 Open job", url=upwork_link),
            ]
        ]
    )


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


async def notify_new_job(bot: Bot, job: Job) -> None:
    settings = get_settings()
    text = (
        f"<b>{job.title}</b>\n\n"
        f"Fit score: {job.fit_score}/100\n"
        f"{job.short_summary}\n\n"
        f"<i>{job.fit_reasoning}</i>"
    )
    await bot.send_message(
        chat_id=settings.admin_telegram_id,
        text=text,
        reply_markup=_job_keyboard(job.id, job.upwork_link),
    )


@router.callback_query(lambda c: c.data.startswith("gen_proposal:"))
async def handle_generate_proposal(callback: CallbackQuery) -> None:
    job_id = int(callback.data.split(":", 1)[1])
    await callback.answer("Generating proposal...")

    async with AsyncSessionLocal() as session:
        job = await get_job(session, job_id)
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
        )

        await save_proposal(session, job_id=job.id, version=1, content=content)

    await callback.message.answer(content, reply_markup=_regenerate_keyboard(job_id))

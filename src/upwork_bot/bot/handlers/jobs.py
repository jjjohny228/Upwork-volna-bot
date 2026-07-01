from aiogram import Bot, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from upwork_bot.config import get_settings
from upwork_bot.db.models import Job

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

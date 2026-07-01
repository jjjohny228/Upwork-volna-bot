import asyncio
import logging

from upwork_bot.bot.handlers.jobs import notify_new_job
from upwork_bot.bot.main import create_bot, create_dispatcher
from upwork_bot.config import get_settings
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import get_active_resume, save_job_analysis
from upwork_bot.llm.analysis_chain import analyze_job
from upwork_bot.rss.poller import run_forever

logging.basicConfig(level=logging.INFO)


async def _on_new_job(bot, job: Job) -> None:
    async with AsyncSessionLocal() as session:
        resume_text = await get_active_resume(session) or ""

    fit = await analyze_job(
        resume_text=resume_text,
        job_title=job.title,
        job_description=job.description,
        categories=job.categories,
    )

    async with AsyncSessionLocal() as session:
        await save_job_analysis(session, job.id, fit)
        job.fit_score = fit.fit_score
        job.short_summary = fit.short_summary
        job.fit_reasoning = fit.reasoning

    await notify_new_job(bot, job)


async def main() -> None:
    settings = get_settings()
    bot = create_bot()
    dispatcher = create_dispatcher()

    async def on_new_job(job: Job) -> None:
        await _on_new_job(bot, job)

    await asyncio.gather(
        dispatcher.start_polling(bot),
        run_forever(settings.poll_interval_seconds, on_new_job),
    )


if __name__ == "__main__":
    asyncio.run(main())

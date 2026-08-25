import asyncio
import logging

from dotenv import load_dotenv

from upwork_bot.bot.handlers.jobs import notify_new_job
from upwork_bot.bot.main import create_bot, create_dispatcher
from upwork_bot.config import get_settings
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import get_user, save_job_analysis
from upwork_bot.gmail.poller import run_forever
from upwork_bot.llm.analysis_chain import qualify_job

logging.basicConfig(level=logging.INFO)


async def _on_new_job(bot, job: Job) -> None:
    # Qualify against the job owner's personalized prompt (falls back to default).
    analysis_prompt = None
    if job.user_id is not None:
        async with AsyncSessionLocal() as session:
            owner = await get_user(session, job.user_id)
        if owner is not None:
            analysis_prompt = owner.analysis_prompt

    # Local qualifier is the sole source of truth; drives the loud/silent notify.
    qualification = await qualify_job(
        job_title=job.title,
        job_description=job.description,
        analysis_prompt=analysis_prompt,
    )

    async with AsyncSessionLocal() as session:
        await save_job_analysis(session, job.id, qualification)
        job.qualified = qualification.qualified
        job.short_summary = qualification.short_summary
        job.fit_reasoning = qualification.reason

    await notify_new_job(bot, job)


async def main() -> None:
    # Export .env into the process environment so LangChain/LangSmith pick up the
    # LANGSMITH_* tracing vars (they read os.environ directly, not our Settings).
    load_dotenv()
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

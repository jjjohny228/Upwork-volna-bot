from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from upwork_bot.db.models import Feed, Job, Resume
from upwork_bot.llm.analysis_chain import JobFit
from upwork_bot.rss.client import RssJob


async def insert_job_if_new(session: AsyncSession, feed_id: int, rss_job: RssJob) -> Job | None:
    stmt = (
        pg_insert(Job)
        .values(
            feed_id=feed_id,
            external_pid=rss_job.external_pid,
            title=rss_job.title,
            description=rss_job.description,
            upwork_link=rss_job.upwork_link,
            categories=rss_job.categories,
            pub_date=rss_job.pub_date,
            status="new",
        )
        .on_conflict_do_nothing(index_elements=["external_pid"])
        .returning(Job)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one_or_none()


async def get_active_feeds(session: AsyncSession):
    result = await session.execute(select(Feed).where(Feed.is_active.is_(True)))
    return list(result.scalars())


async def add_feed(session: AsyncSession, url: str, label: str) -> Feed:
    feed = Feed(url=url, label=label)
    session.add(feed)
    await session.commit()
    await session.refresh(feed)
    return feed


async def remove_feed(session: AsyncSession, feed_id: int) -> bool:
    feed = await session.get(Feed, feed_id)
    if feed is None:
        return False
    await session.delete(feed)
    await session.commit()
    return True


async def list_feeds(session: AsyncSession) -> list[Feed]:
    result = await session.execute(select(Feed))
    return list(result.scalars())


async def get_active_resume(session: AsyncSession) -> str | None:
    result = await session.execute(select(Resume).order_by(Resume.updated_at.desc()).limit(1))
    resume = result.scalars().first()
    return resume.content if resume else None


async def save_job_analysis(session: AsyncSession, job_id: int, fit: JobFit) -> None:
    job = await session.get(Job, job_id)
    job.fit_score = fit.fit_score
    job.short_summary = fit.short_summary
    job.fit_reasoning = fit.reasoning
    job.status = "analyzed"
    await session.commit()

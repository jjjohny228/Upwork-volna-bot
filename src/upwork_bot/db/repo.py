from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from upwork_bot.db.models import Feed, Job
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

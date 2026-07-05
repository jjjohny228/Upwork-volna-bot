from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from upwork_bot.db.models import (
    Feed,
    Job,
    PortfolioProject,
    Proposal,
    ProposalExample,
    Resume,
)
from upwork_bot.rss.client import RssJob

if TYPE_CHECKING:
    from upwork_bot.llm.analysis_chain import JobFit


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


async def save_job_analysis(session: AsyncSession, job_id: int, fit: "JobFit") -> None:
    job = await session.get(Job, job_id)
    job.fit_score = fit.fit_score
    job.short_summary = fit.short_summary
    job.fit_reasoning = fit.reasoning
    job.status = "analyzed"
    await session.commit()


async def upsert_resume(session: AsyncSession, content: str) -> None:
    resume = Resume(content=content)
    session.add(resume)
    await session.commit()


async def add_portfolio_project(
    session: AsyncSession,
    title: str,
    description: str,
    link: str | None,
    embedding: list[float],
) -> PortfolioProject:
    project = PortfolioProject(title=title, description=description, link=link, embedding=embedding)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def add_proposal_example(
    session: AsyncSession, source_text: str, embedding: list[float]
) -> ProposalExample:
    example = ProposalExample(source_text=source_text, embedding=embedding)
    session.add(example)
    await session.commit()
    await session.refresh(example)
    return example


async def list_portfolio_projects(session: AsyncSession) -> list[PortfolioProject]:
    result = await session.execute(select(PortfolioProject))
    return list(result.scalars())


async def remove_portfolio_project(session: AsyncSession, project_id: int) -> bool:
    project = await session.get(PortfolioProject, project_id)
    if project is None:
        return False
    await session.delete(project)
    await session.commit()
    return True


async def list_proposal_examples(session: AsyncSession) -> list[ProposalExample]:
    result = await session.execute(select(ProposalExample))
    return list(result.scalars())


async def remove_proposal_example(session: AsyncSession, example_id: int) -> bool:
    example = await session.get(ProposalExample, example_id)
    if example is None:
        return False
    await session.delete(example)
    await session.commit()
    return True


async def search_similar_portfolio(
    session: AsyncSession, embedding: list[float], top_k: int = 3
) -> list[PortfolioProject]:
    stmt = (
        select(PortfolioProject)
        .order_by(PortfolioProject.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def search_similar_examples(
    session: AsyncSession, embedding: list[float], top_k: int = 3
) -> list[ProposalExample]:
    stmt = (
        select(ProposalExample)
        .order_by(ProposalExample.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def get_job(session: AsyncSession, job_id: int) -> Job | None:
    return await session.get(Job, job_id)


async def get_latest_proposal(session: AsyncSession, job_id: int) -> Proposal | None:
    stmt = (
        select(Proposal).where(Proposal.job_id == job_id).order_by(Proposal.version.desc()).limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def save_proposal(
    session: AsyncSession,
    job_id: int,
    version: int,
    content: str,
    user_feedback: str | None = None,
) -> Proposal:
    proposal = Proposal(
        job_id=job_id, version=version, content=content, user_feedback=user_feedback
    )
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return proposal

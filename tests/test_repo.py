import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed, Job, PortfolioProject, ProposalExample
from upwork_bot.db.repo import (
    insert_job_if_new,
    list_portfolio_projects,
    list_proposal_examples,
    remove_portfolio_project,
    remove_proposal_example,
)
from upwork_bot.rss.client import RssJob


@pytest.mark.asyncio
async def test_insert_job_if_new_dedupes_by_pid():
    async with AsyncSessionLocal() as session:
        feed = Feed(url="https://vollna.com/rss/dedup-test", label="dedup-test")
        session.add(feed)
        await session.commit()

        rss_job = RssJob(
            external_pid="dedup-pid-1",
            title="t",
            description="d",
            upwork_link="https://upwork.com/jobs/~1",
        )

        first = await insert_job_if_new(session, feed.id, rss_job)
        second = await insert_job_if_new(session, feed.id, rss_job)

        assert first is not None
        assert second is None

        result = await session.execute(select(Job).where(Job.external_pid == "dedup-pid-1"))
        rows = list(result.scalars())
        assert len(rows) == 1

        await session.delete(rows[0])
        await session.delete(feed)
        await session.commit()


@pytest.mark.asyncio
async def test_list_and_remove_portfolio_project():
    async with AsyncSessionLocal() as session:
        project = PortfolioProject(
            title="repo-test-project",
            description="d",
            link=None,
            embedding=[0.0] * 1536,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        projects = await list_portfolio_projects(session)
        assert any(p.id == project.id for p in projects)

        removed = await remove_portfolio_project(session, project.id)
        assert removed is True

        removed_again = await remove_portfolio_project(session, project.id)
        assert removed_again is False

        projects_after = await list_portfolio_projects(session)
        assert all(p.id != project.id for p in projects_after)


@pytest.mark.asyncio
async def test_list_and_remove_proposal_example():
    async with AsyncSessionLocal() as session:
        example = ProposalExample(source_text="repo-test-example", embedding=[0.0] * 1536)
        session.add(example)
        await session.commit()
        await session.refresh(example)

        examples = await list_proposal_examples(session)
        assert any(e.id == example.id for e in examples)

        removed = await remove_proposal_example(session, example.id)
        assert removed is True

        removed_again = await remove_proposal_example(session, example.id)
        assert removed_again is False

        examples_after = await list_proposal_examples(session)
        assert all(e.id != example.id for e in examples_after)

import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job, PortfolioProject, ProposalExample
from upwork_bot.db.repo import (
    add_user,
    delete_user,
    get_or_create_admin_user,
    get_user_by_telegram_id,
    insert_job_if_new,
    list_portfolio_projects,
    list_proposal_examples,
    list_users,
    remove_portfolio_project,
    remove_proposal_example,
    set_active,
    set_notify_qualified_only,
)
from upwork_bot.gmail.client import JobEmail


@pytest.mark.asyncio
async def test_insert_job_if_new_dedupes_by_pid():
    async with AsyncSessionLocal() as session:
        admin = await get_or_create_admin_user(session, 617073201)
        job_email = JobEmail(
            external_pid="dedup-pid-1",
            title="t",
            description="d",
            upwork_link="https://www.upwork.com/jobs/~1",
            rate="Hourly Rate: 10 - 20 USD",
        )

        first = await insert_job_if_new(session, job_email, admin.id)
        second = await insert_job_if_new(session, job_email, admin.id)

        assert first is not None
        assert second is None

        result = await session.execute(select(Job).where(Job.external_pid == "dedup-pid-1"))
        rows = list(result.scalars())
        assert len(rows) == 1

        await session.delete(rows[0])
        await session.commit()


@pytest.mark.asyncio
async def test_same_pid_two_users_makes_two_jobs():
    async with AsyncSessionLocal() as session:
        admin = await get_or_create_admin_user(session, 617073201)
        other = await add_user(session, telegram_id=999_000_111, display_name="other")
        job_email = JobEmail(
            external_pid="shared-pid-1",
            title="t",
            description="d",
            upwork_link="https://www.upwork.com/jobs/~9",
        )

        a = await insert_job_if_new(session, job_email, admin.id)
        b = await insert_job_if_new(session, job_email, other.id)

        assert a is not None and b is not None
        assert a.id != b.id

        result = await session.execute(select(Job).where(Job.external_pid == "shared-pid-1"))
        rows = list(result.scalars())
        assert len(rows) == 2

        for row in rows:
            await session.delete(row)
        await session.commit()
        await delete_user(session, 999_000_111)


@pytest.mark.asyncio
async def test_user_crud_and_toggle():
    tid = 999_000_222
    async with AsyncSessionLocal() as session:
        await delete_user(session, tid)  # ensure clean slate

        created = await add_user(session, telegram_id=tid, display_name="crud")
        assert created.telegram_id == tid
        assert created.is_active is True
        assert created.notify_qualified_only is False

        fetched = await get_user_by_telegram_id(session, tid)
        assert fetched is not None and fetched.id == created.id
        assert any(u.telegram_id == tid for u in await list_users(session))

        # add_user is idempotent + reactivates.
        assert await set_active(session, tid, False) is True
        again = await add_user(session, telegram_id=tid, display_name="crud")
        assert again.id == created.id
        assert again.is_active is True

        assert await set_notify_qualified_only(session, tid, True) is True
        toggled = await get_user_by_telegram_id(session, tid)
        assert toggled.notify_qualified_only is True

        assert await delete_user(session, tid) is True
        assert await get_user_by_telegram_id(session, tid) is None
        assert await set_active(session, tid, True) is False
        assert await set_notify_qualified_only(session, tid, True) is False


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

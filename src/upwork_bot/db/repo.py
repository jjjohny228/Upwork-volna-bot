from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from upwork_bot.db.models import (
    Job,
    PortfolioProject,
    Proposal,
    ProposalExample,
    Resume,
    User,
)
from upwork_bot.gmail.client import JobEmail

if TYPE_CHECKING:
    from upwork_bot.llm.analysis_chain import JobQualification


# --- Users -----------------------------------------------------------------


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalars().first()


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars())


async def add_user(
    session: AsyncSession, telegram_id: int, display_name: str | None = None
) -> User:
    """Insert a user (idempotent on telegram_id); reactivates an existing row."""
    stmt = (
        pg_insert(User)
        .values(telegram_id=telegram_id, display_name=display_name, is_active=True)
        .on_conflict_do_update(
            index_elements=["telegram_id"],
            set_={"is_active": True},
        )
        .returning(User)
    )
    result = await session.execute(stmt)
    user = result.scalar_one()
    await session.commit()
    # RETURNING won't overwrite an already-identity-mapped instance's in-memory
    # state (e.g. a prior is_active flip), so refresh to reflect the upsert.
    await session.refresh(user)
    return user


async def set_active(session: AsyncSession, telegram_id: int, is_active: bool) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.is_active = is_active
    await session.commit()
    return True


async def delete_user(session: AsyncSession, telegram_id: int) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    await session.delete(user)
    await session.commit()
    return True


async def get_or_create_admin_user(session: AsyncSession, admin_telegram_id: int) -> User:
    user = await get_user_by_telegram_id(session, admin_telegram_id)
    if user is not None:
        return user
    return await add_user(session, admin_telegram_id, display_name="admin")


async def set_notify_qualified_only(
    session: AsyncSession, telegram_id: int, qualified_only: bool
) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.notify_qualified_only = qualified_only
    await session.commit()
    return True


# --- Jobs ------------------------------------------------------------------


async def insert_job_if_new(session: AsyncSession, job_email: JobEmail, user_id: int) -> Job | None:
    stmt = (
        pg_insert(Job)
        .values(
            user_id=user_id,
            external_pid=job_email.external_pid,
            title=job_email.title,
            description=job_email.description,
            upwork_link=job_email.upwork_link,
            categories=[],
            rate=job_email.rate,
            pub_date=job_email.pub_date,
            status="new",
        )
        .on_conflict_do_nothing(index_elements=["user_id", "external_pid"])
        .returning(Job)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one_or_none()


async def get_active_resume(session: AsyncSession) -> str | None:
    result = await session.execute(select(Resume).order_by(Resume.updated_at.desc()).limit(1))
    resume = result.scalars().first()
    return resume.content if resume else None


async def get_active_resume_pdf(session: AsyncSession) -> bytes | None:
    result = await session.execute(select(Resume).order_by(Resume.updated_at.desc()).limit(1))
    resume = result.scalars().first()
    return resume.pdf_bytes if resume else None


async def save_job_analysis(
    session: AsyncSession, job_id: int, qualification: "JobQualification"
) -> None:
    job = await session.get(Job, job_id)
    job.qualified = qualification.qualified
    job.short_summary = qualification.short_summary
    job.fit_reasoning = qualification.reason
    job.status = "analyzed"
    await session.commit()


async def upsert_resume(
    session: AsyncSession, content: str, pdf_bytes: bytes | None = None
) -> None:
    resume = Resume(content=content, pdf_bytes=pdf_bytes)
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

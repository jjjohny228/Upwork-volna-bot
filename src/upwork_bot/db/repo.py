from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from upwork_bot.db.models import (
    Job,
    Mailbox,
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


async def set_hourly_rate(session: AsyncSession, telegram_id: int, rate: float) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.hourly_rate = rate
    await session.commit()
    return True


async def set_signature_name(session: AsyncSession, telegram_id: int, name: str) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.signature_name = name
    await session.commit()
    return True


async def set_analysis_prompt(session: AsyncSession, telegram_id: int, prompt: str) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.analysis_prompt = prompt
    await session.commit()
    return True


async def set_timezone(session: AsyncSession, telegram_id: int, tz: str) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.timezone = tz
    await session.commit()
    return True


async def set_parsing_active(session: AsyncSession, telegram_id: int, active: bool) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.parsing_active = active
    await session.commit()
    return True


async def set_quiet_hours_enabled(session: AsyncSession, telegram_id: int, enabled: bool) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.quiet_hours_enabled = enabled
    await session.commit()
    return True


async def set_quiet_window(session: AsyncSession, telegram_id: int, start: time, end: time) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.quiet_start = start
    user.quiet_end = end
    await session.commit()
    return True


# --- Mailboxes -------------------------------------------------------------


async def list_active_mailboxes(session: AsyncSession) -> list[Mailbox]:
    result = await session.execute(
        select(Mailbox).where(Mailbox.is_active.is_(True)).order_by(Mailbox.id)
    )
    return list(result.scalars())


async def list_user_mailboxes(session: AsyncSession, user_id: int) -> list[Mailbox]:
    result = await session.execute(
        select(Mailbox).where(Mailbox.user_id == user_id).order_by(Mailbox.id)
    )
    return list(result.scalars())


async def add_mailbox(
    session: AsyncSession,
    user_id: int,
    address: str,
    app_password: str,
    mailbox: str = "INBOX",
    imap_host: str = "imap.gmail.com",
) -> Mailbox:
    row = Mailbox(
        user_id=user_id,
        address=address,
        app_password=app_password,
        mailbox=mailbox,
        imap_host=imap_host,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def remove_mailbox(session: AsyncSession, mailbox_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(Mailbox).where(Mailbox.id == mailbox_id, Mailbox.user_id == user_id)
    )
    row = result.scalars().first()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def set_mailbox_cursor(session: AsyncSession, mailbox_id: int, cursor: str) -> None:
    row = await session.get(Mailbox, mailbox_id)
    if row is not None:
        row.cursor = cursor
        await session.commit()


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


async def get_active_resume(session: AsyncSession, user_id: int) -> str | None:
    result = await session.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.updated_at.desc()).limit(1)
    )
    resume = result.scalars().first()
    return resume.content if resume else None


async def get_active_resume_pdf(session: AsyncSession, user_id: int) -> bytes | None:
    result = await session.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.updated_at.desc()).limit(1)
    )
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
    session: AsyncSession, user_id: int, content: str, pdf_bytes: bytes | None = None
) -> None:
    # One resume per user: replace any existing row(s) for this user.
    existing = await session.execute(select(Resume).where(Resume.user_id == user_id))
    for row in existing.scalars():
        await session.delete(row)
    session.add(Resume(user_id=user_id, content=content, pdf_bytes=pdf_bytes))
    await session.commit()


async def add_portfolio_project(
    session: AsyncSession,
    user_id: int,
    title: str,
    description: str,
    link: str | None,
    embedding: list[float],
) -> PortfolioProject:
    project = PortfolioProject(
        user_id=user_id, title=title, description=description, link=link, embedding=embedding
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def add_proposal_example(
    session: AsyncSession, user_id: int, source_text: str, embedding: list[float]
) -> ProposalExample:
    example = ProposalExample(user_id=user_id, source_text=source_text, embedding=embedding)
    session.add(example)
    await session.commit()
    await session.refresh(example)
    return example


async def list_portfolio_projects(session: AsyncSession, user_id: int) -> list[PortfolioProject]:
    result = await session.execute(
        select(PortfolioProject).where(PortfolioProject.user_id == user_id)
    )
    return list(result.scalars())


async def remove_portfolio_project(session: AsyncSession, project_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(PortfolioProject).where(
            PortfolioProject.id == project_id, PortfolioProject.user_id == user_id
        )
    )
    project = result.scalars().first()
    if project is None:
        return False
    await session.delete(project)
    await session.commit()
    return True


async def list_proposal_examples(session: AsyncSession, user_id: int) -> list[ProposalExample]:
    result = await session.execute(
        select(ProposalExample).where(ProposalExample.user_id == user_id)
    )
    return list(result.scalars())


async def remove_proposal_example(session: AsyncSession, example_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(ProposalExample).where(
            ProposalExample.id == example_id, ProposalExample.user_id == user_id
        )
    )
    example = result.scalars().first()
    if example is None:
        return False
    await session.delete(example)
    await session.commit()
    return True


async def search_similar_portfolio(
    session: AsyncSession, user_id: int, embedding: list[float], top_k: int = 3
) -> list[PortfolioProject]:
    stmt = (
        select(PortfolioProject)
        .where(PortfolioProject.user_id == user_id)
        .order_by(PortfolioProject.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def search_similar_examples(
    session: AsyncSession, user_id: int, embedding: list[float], top_k: int = 3
) -> list[ProposalExample]:
    stmt = (
        select(ProposalExample)
        .where(ProposalExample.user_id == user_id)
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

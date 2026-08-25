from datetime import datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    LargeBinary,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from upwork_bot.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    signature_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Job delivery mode: when true, only qualified jobs are pushed to the user;
    # when false (default), every job is pushed (disqualified ones arrive silently).
    notify_qualified_only: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Per-user parsing schedule. `parsing_active` is the manual start/pause switch;
    # quiet hours suspend parsing during a daily local-time window (needs timezone).
    parsing_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    quiet_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Mailbox(Base):
    __tablename__ = "mailboxes"
    __table_args__ = (UniqueConstraint("user_id", "address", name="uq_mailboxes_user_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    address: Mapped[str] = mapped_column(Text)
    app_password: Mapped[str] = mapped_column(Text)
    mailbox: Mapped[str] = mapped_column(Text, default="INBOX", server_default="INBOX")
    imap_host: Mapped[str] = mapped_column(
        Text, default="imap.gmail.com", server_default="imap.gmail.com"
    )
    # Per-mailbox watermark (ISO datetime): only emails at/after this are processed.
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "external_pid", name="uq_jobs_user_external_pid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    external_pid: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    upwork_link: Mapped[str] = mapped_column(Text)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    rate: Mapped[str | None] = mapped_column(Text, nullable=True)
    pub_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    qualified: Mapped[bool | None] = mapped_column(nullable=True)
    fit_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="new")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    proposals: Mapped[list["Proposal"]] = relationship(back_populates="job")


class Resume(Base):
    __tablename__ = "resume"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text)
    pdf_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PortfolioProject(Base):
    __tablename__ = "portfolio_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProposalExample(Base):
    __tablename__ = "proposal_examples"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    version: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    job: Mapped["Job"] = relationship(back_populates="proposals")

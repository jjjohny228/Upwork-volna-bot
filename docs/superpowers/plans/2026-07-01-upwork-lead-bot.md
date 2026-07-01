# Upwork Job-Hunter Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Single-user Telegram bot that polls Vollna RSS feeds, stores every job in Postgres, scores fit + summarizes via LLM, pushes Telegram cards with action buttons, and generates/regenerates Upwork proposal drafts via RAG over resume/portfolio/past proposals.

**Architecture:** aiogram long-polling bot + asyncio RSS poller run together from one `asyncio.gather` in `app.py`. SQLAlchemy 2.0 async ORM over Postgres+pgvector (asyncpg driver), Alembic migrations. LangChain `ChatOpenAI` for structured analysis and RAG proposal generation, `OpenAIEmbeddings` (`text-embedding-3-small`) for embeddings. Everything owner-gated via aiogram middleware. Deployed as `bot` + `db` services in one `docker-compose.yml`.

**Tech Stack:** Python 3.12, uv, aiogram 3.x, SQLAlchemy 2.0 (asyncio) + asyncpg, alembic, pgvector (Postgres extension + `pgvector` python package), langchain + langchain-openai, pydantic-settings, stdlib `xml.etree.ElementTree` for RSS, pypdf + docx2txt for resume upload, ruff, pytest + pytest-asyncio, docker-compose with `pgvector/pgvector:pg16`.

## Global Constraints

- Python version: 3.12 (pyproject `requires-python = ">=3.12"`).
- Package/env manager: `uv` only — no pip/poetry/conda commands anywhere.
- Lint/format: `ruff check` and `ruff format --check` must be clean before each commit.
- Single-user bot: every handler must be gated by owner-only middleware comparing `message.from_user.id` (or `callback_query.from_user.id`) to `settings.admin_telegram_id`.
- Poll interval must default to 180s and be configurable via `POLL_INTERVAL_SECONDS` env var; must stay well under Vollna's ~10 minute feed expiry.
- Dedup key is the `pid` query parameter parsed out of the Vollna `link` field — never dedupe on title/description.
- The Upwork "Open job" button must link to the decoded real Upwork URL (the double-URL-decoded `url=` param inside the Vollna redirect link), never the raw `vollna.com/go?...` redirect.
- All DB access is async (asyncpg driver, SQLAlchemy `AsyncSession`) — no sync `psycopg2` anywhere.
- Embedding dimension is fixed at 1536 (`text-embedding-3-small`) — `Vector(1536)` everywhere it's used.
- No index-tuning beyond a plain `ivfflat` note in the migration comment — do not build an index-selection framework for an MVP with a handful of rows.
- Every module lives under `src/upwork_bot/` per the layout below — do not flatten or reorganize it.
- Secrets only via `.env` (pydantic-settings `BaseSettings`), never hardcoded, never logged.

---

## File Structure

```
upwork-lead-bot/                    (built inside current dir: /Users/gleb/PycharmProjects/upwork-vollna-bot)
  pyproject.toml
  docker-compose.yml
  Dockerfile
  .env.example
  .gitignore
  alembic.ini
  migrations/
    env.py
    versions/0001_initial.py
  src/upwork_bot/
    __init__.py
    config.py
    db/
      __init__.py
      base.py
      models.py
      repo.py
    rss/
      __init__.py
      client.py
      poller.py
    llm/
      __init__.py
      embeddings.py
      analysis_chain.py
      proposal_chain.py
    bot/
      __init__.py
      main.py
      middlewares/
        __init__.py
        owner_only.py
      handlers/
        __init__.py
        jobs.py
        proposals.py
        feeds.py
        resume.py
        portfolio.py
        proposal_examples.py
    app.py
  tests/
    __init__.py
    conftest.py
    test_rss_client.py
    test_repo.py
    test_analysis_chain.py
    test_proposal_chain.py
    test_owner_only.py
```

Rationale: `db/` isolates persistence (models + queries), `rss/` isolates feed I/O, `llm/` isolates all OpenAI/LangChain calls (mockable in tests), `bot/` isolates aiogram wiring — each handler file maps 1:1 to a command group from the spec so they can be reviewed/extended independently. `app.py` is the single entrypoint that starts poller + bot together.

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/upwork_bot/__init__.py`
- Create: `src/upwork_bot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `upwork_bot.config.Settings` pydantic-settings class with fields `bot_token: str`, `admin_telegram_id: int`, `database_url: str`, `openai_api_key: str`, `poll_interval_seconds: int = 180`. Module-level `get_settings()` cached factory (`functools.lru_cache`).

- [ ] **Step 1: Init uv project**

Run:
```bash
cd /Users/gleb/PycharmProjects/upwork-vollna-bot
uv init --name upwork-bot --python 3.12 --no-readme
rm -f main.py hello.py
```

- [ ] **Step 2: Write pyproject.toml dependencies + ruff config**

```toml
[project]
name = "upwork-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "aiogram>=3.15,<4",
    "sqlalchemy[asyncio]>=2.0,<3",
    "asyncpg>=0.30,<1",
    "alembic>=1.14,<2",
    "pgvector>=0.3.6,<1",
    "langchain>=0.3,<0.4",
    "langchain-openai>=0.2,<0.3",
    "pydantic-settings>=2.6,<3",
    "pypdf>=5.1,<6",
    "docx2txt>=0.8,<1",
]

[dependency-groups]
dev = [
    "pytest>=8.3,<9",
    "pytest-asyncio>=0.24,<1",
    "ruff>=0.8,<1",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Run:
```bash
uv sync
```

- [ ] **Step 3: Write .env.example**

```
BOT_TOKEN=123456:ABC-DEF...
ADMIN_TELEGRAM_ID=123456789
DATABASE_URL=postgresql+asyncpg://upwork:upwork@db:5432/upwork
OPENAI_API_KEY=sk-...
POLL_INTERVAL_SECONDS=180
```

- [ ] **Step 4: Write .gitignore**

```
.venv/
__pycache__/
*.pyc
.env
.idea/
```

- [ ] **Step 5: Write config.py**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    admin_telegram_id: int
    database_url: str
    openai_api_key: str
    poll_interval_seconds: int = 180


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Write failing-then-passing config test**

`tests/__init__.py` (empty file), then `tests/test_config.py`:

```python
import os

from upwork_bot.config import Settings


def test_settings_reads_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "42")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.bot_token == "test-token"
    assert settings.admin_telegram_id == 42
    assert settings.poll_interval_seconds == 180
```

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (4 assertions, no external file needed since env vars are set directly)

- [ ] **Step 7: Lint check**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: no errors (run `uv run ruff format .` once to auto-fix style if it complains)

- [ ] **Step 8: Commit**

```bash
git init
git add pyproject.toml uv.lock .env.example .gitignore src tests
git commit -m "chore: scaffold uv project with pydantic-settings config"
```

---

## Task 2: Docker Compose + Postgres/pgvector

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: `Settings` from Task 1 (env vars passed through compose `environment:`/`env_file:`).
- Produces: running `db` service reachable at `postgresql+asyncpg://upwork:upwork@db:5432/upwork` from inside the `bot` container network, and at `localhost:5433` from the host (mapped to avoid clashing with any local Postgres on 5432).

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "python", "-m", "upwork_bot.app"]
```

- [ ] **Step 2: Write docker-compose.yml**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: upwork
      POSTGRES_PASSWORD: upwork
      POSTGRES_DB: upwork
    ports:
      - "5433:5432"
    volumes:
      - upwork_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U upwork"]
      interval: 5s
      timeout: 5s
      retries: 10

  bot:
    build: .
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env

volumes:
  upwork_db_data:
```

- [ ] **Step 3: Bring up db only and verify**

Run:
```bash
docker compose up -d db
docker compose exec db psql -U upwork -d upwork -c "SELECT 1;"
```
Expected: prints `1` under `?column?`

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore: add docker-compose for bot + pgvector postgres"
```

---

## Task 3: DB Models + First Migration

**Files:**
- Create: `src/upwork_bot/db/__init__.py`
- Create: `src/upwork_bot/db/base.py`
- Create: `src/upwork_bot/db/models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/0001_initial.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `Settings.database_url` from Task 1.
- Produces: `Base` (declarative base) and ORM classes `Feed`, `Job`, `Resume`, `PortfolioProject`, `ProposalExample`, `Proposal` in `db.models`; `async_engine`, `AsyncSessionLocal` (async_sessionmaker) in `db.base`.

- [ ] **Step 1: Write db/base.py**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from upwork_bot.config import get_settings


class Base:
    pass


from sqlalchemy.orm import DeclarativeBase  # noqa: E402


class Base(DeclarativeBase):  # noqa: F811
    pass


engine = create_async_engine(get_settings().database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

(Note: write it cleanly, the duplicate `Base` above is only illustrative — see Step 1a.)

- [ ] **Step 1a: Clean version to actually write to disk**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from upwork_bot.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

- [ ] **Step 2: Write db/models.py**

```python
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from upwork_bot.db.base import Base


class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    label: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    jobs: Mapped[list["Job"]] = relationship(back_populates="feed")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("external_pid", name="uq_jobs_external_pid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id"))
    external_pid: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    upwork_link: Mapped[str] = mapped_column(Text)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    pub_date: Mapped[datetime | None] = mapped_column(nullable=True)
    fit_score: Mapped[int | None] = mapped_column(nullable=True)
    fit_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="new")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    feed: Mapped["Feed"] = relationship(back_populates="jobs")
    proposals: Mapped[list["Proposal"]] = relationship(back_populates="job")


class Resume(Base):
    __tablename__ = "resume"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PortfolioProject(Base):
    __tablename__ = "portfolio_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProposalExample(Base):
    __tablename__ = "proposal_examples"

    id: Mapped[int] = mapped_column(primary_key=True)
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
```

- [ ] **Step 3: Init alembic and configure for async**

Run:
```bash
uv run alembic init migrations
```

Edit `alembic.ini`: delete the `sqlalchemy.url = ...` line (URL comes from `Settings` at runtime, not a hardcoded ini value).

Replace `migrations/env.py` with:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from upwork_bot.config import get_settings
from upwork_bot.db.base import Base
from upwork_bot.db import models  # noqa: F401  (import to register mappers)

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Write the initial migration by hand (autogenerate can't create the `vector` extension)**

`migrations/versions/0001_initial.py`:

```python
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-01
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("feed_id", sa.Integer, sa.ForeignKey("feeds.id"), nullable=False),
        sa.Column("external_pid", sa.Text, nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("upwork_link", sa.Text, nullable=False),
        sa.Column("categories", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("pub_date", sa.DateTime, nullable=True),
        sa.Column("fit_score", sa.Integer, nullable=True),
        sa.Column("fit_reasoning", sa.Text, nullable=True),
        sa.Column("short_summary", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "resume",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "portfolio_projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("link", sa.Text, nullable=True),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "proposal_examples",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("user_feedback", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    # Note: skip ivfflat index on embedding columns for now — MVP will have a
    # handful of rows; add `CREATE INDEX ... USING ivfflat (embedding vector_cosine_ops)`
    # in a later migration once proposal_examples/portfolio_projects grow large.


def downgrade() -> None:
    op.drop_table("proposals")
    op.drop_table("proposal_examples")
    op.drop_table("portfolio_projects")
    op.drop_table("resume")
    op.drop_table("jobs")
    op.drop_table("feeds")
```

- [ ] **Step 5: Apply migration against the running db**

Requires a `.env` with a real `DATABASE_URL` pointing at `localhost:5433` for local (non-container) alembic runs. Create `.env` from `.env.example` and set `DATABASE_URL=postgresql+asyncpg://upwork:upwork@localhost:5433/upwork`.

Run:
```bash
uv run alembic upgrade head
docker compose exec db psql -U upwork -d upwork -c "\dt"
```
Expected: lists `feeds, jobs, resume, portfolio_projects, proposal_examples, proposals`

- [ ] **Step 6: Write model smoke test (requires live db)**

```python
import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed


@pytest.mark.asyncio
async def test_insert_and_query_feed():
    async with AsyncSessionLocal() as session:
        feed = Feed(url="https://vollna.com/rss/test-unique-123", label="test")
        session.add(feed)
        await session.commit()

        result = await session.execute(select(Feed).where(Feed.url == feed.url))
        loaded = result.scalar_one()
        assert loaded.label == "test"
        assert loaded.is_active is True

        await session.delete(loaded)
        await session.commit()
```

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (requires `docker compose up -d db` running and migration applied)

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/db alembic.ini migrations tests/test_models.py
git commit -m "feat: add db models and initial pgvector migration"
```

---

## Task 4: RSS Client + Dedup Repo Functions

**Files:**
- Create: `src/upwork_bot/rss/__init__.py`
- Create: `src/upwork_bot/rss/client.py`
- Create: `src/upwork_bot/db/repo.py`
- Test: `tests/test_rss_client.py`
- Test: `tests/test_repo.py`

**Interfaces:**
- Produces: `rss.client.RssJob` dataclass (`external_pid: str`, `title: str`, `description: str`, `upwork_link: str`, `categories: list[str]`, `pub_date: datetime | None`) and `rss.client.fetch_feed(url: str) -> list[RssJob]` (async, uses `httpx`... actually spec says no new HTTP lib beyond stdlib mentioned — use `urllib.request` in a thread via `asyncio.to_thread`, or add `httpx` as a light dep since spec's dep list doesn't list it explicitly but async HTTP is required; add `httpx>=0.27,<1` to pyproject in Step 0 below).
- Produces: `db.repo.insert_job_if_new(session, feed_id: int, rss_job: RssJob) -> Job | None` — returns the created `Job` or `None` if `external_pid` already exists (catches unique-violation).
- Consumes: `db.models.Job`, `db.base.AsyncSessionLocal` from Task 3.

- [ ] **Step 0: Add httpx dependency**

Run:
```bash
uv add httpx
```

- [ ] **Step 1: Write failing test for link parsing (pid + double-decoded url)**

```python
from upwork_bot.rss.client import parse_vollna_link

SAMPLE_LINK = (
    "https://www.vollna.com/go?"
    "pid=abc123def&"
    "url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~0123456789abcdef"
)


def test_parse_vollna_link_extracts_pid_and_decoded_url():
    pid, real_url = parse_vollna_link(SAMPLE_LINK)

    assert pid == "abc123def"
    assert real_url == "https://www.upwork.com/jobs/~0123456789abcdef"
```

Run: `uv run pytest tests/test_rss_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_vollna_link'`

- [ ] **Step 2: Write rss/client.py**

```python
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, unquote, urlparse

import httpx


@dataclass
class RssJob:
    external_pid: str
    title: str
    description: str
    upwork_link: str
    categories: list[str] = field(default_factory=list)
    pub_date: datetime | None = None


def parse_vollna_link(link: str) -> tuple[str, str]:
    query = parse_qs(urlparse(link).query)
    pid = query["pid"][0]
    encoded_url = query["url"][0]
    # Vollna double-URL-encodes the target Upwork link.
    real_url = unquote(unquote(encoded_url))
    return pid, real_url


def _parse_pub_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def _parse_item(item: ET.Element) -> RssJob:
    title = (item.findtext("title") or "").strip()
    description = (item.findtext("description") or "").strip()
    link = (item.findtext("link") or "").strip()
    pub_date = _parse_pub_date(item.findtext("pubDate"))
    categories = [c.text.strip() for c in item.findall("category") if c.text]

    pid, real_url = parse_vollna_link(link)

    return RssJob(
        external_pid=pid,
        title=title,
        description=description,
        upwork_link=real_url,
        categories=categories,
        pub_date=pub_date,
    )


async def fetch_feed(url: str) -> list[RssJob]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()

    root = ET.fromstring(response.text)
    items = root.findall(".//item")
    return [_parse_item(item) for item in items]
```

- [ ] **Step 3: Run test, verify pass**

Run: `uv run pytest tests/test_rss_client.py -v`
Expected: PASS

- [ ] **Step 4: Write failing test for feed item parsing with real-shaped XML**

Append to `tests/test_rss_client.py`:

```python
from upwork_bot.rss.client import _parse_item
import xml.etree.ElementTree as ET

SAMPLE_ITEM_XML = """
<item>
    <title>Need a Python developer</title>
    <description><![CDATA[Looking for someone to build a scraper.]]></description>
    <pubDate>Wed, 01 Jul 2026 12:00:00 GMT</pubDate>
    <link>https://www.vollna.com/go?pid=xyz789&amp;url=https%253A%252F%252Fwww.upwork.com%252Fjobs%252F~999</link>
    <category>Web, Mobile &amp; Software Dev</category>
    <category>Python</category>
</item>
"""


def test_parse_item_extracts_all_fields():
    item = ET.fromstring(SAMPLE_ITEM_XML)
    job = _parse_item(item)

    assert job.external_pid == "xyz789"
    assert job.upwork_link == "https://www.upwork.com/jobs/~999"
    assert job.title == "Need a Python developer"
    assert "scraper" in job.description
    assert job.categories == ["Web, Mobile & Software Dev", "Python"]
    assert job.pub_date is not None
```

Run: `uv run pytest tests/test_rss_client.py -v`
Expected: PASS (implementation from Step 2 already handles this)

- [ ] **Step 5: Write db/repo.py**

```python
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from upwork_bot.db.models import Job
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
    from upwork_bot.db.models import Feed

    result = await session.execute(select(Feed).where(Feed.is_active.is_(True)))
    return list(result.scalars())
```

- [ ] **Step 6: Write repo test (requires live db from Task 3)**

```python
import pytest
from sqlalchemy import select

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed, Job
from upwork_bot.db.repo import insert_job_if_new
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
```

Run: `uv run pytest tests/test_repo.py -v`
Expected: PASS

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/rss src/upwork_bot/db/repo.py tests/test_rss_client.py tests/test_repo.py pyproject.toml uv.lock
git commit -m "feat: add RSS client with pid dedup parsing and repo insert-if-new"
```

---

## Task 5: RSS Poller Loop

**Files:**
- Create: `src/upwork_bot/rss/poller.py`

**Interfaces:**
- Consumes: `rss.client.fetch_feed`, `db.repo.get_active_feeds`, `db.repo.insert_job_if_new`, `db.base.AsyncSessionLocal`.
- Produces: `rss.poller.poll_once(session_factory, on_new_job: Callable[[Job], Awaitable[None]]) -> None` (one pass over all active feeds) and `rss.poller.run_forever(interval_seconds: int, on_new_job) -> None` (loops `poll_once` on a timer, never returns — used by `app.py`).

- [ ] **Step 1: Write rss/poller.py**

```python
import asyncio
import logging
from collections.abc import Awaitable, Callable

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import get_active_feeds, insert_job_if_new
from upwork_bot.rss.client import fetch_feed

logger = logging.getLogger(__name__)

OnNewJob = Callable[[Job], Awaitable[None]]


async def poll_once(on_new_job: OnNewJob) -> int:
    new_count = 0
    async with AsyncSessionLocal() as session:
        feeds = await get_active_feeds(session)

    for feed in feeds:
        try:
            rss_jobs = await fetch_feed(feed.url)
        except Exception:
            logger.exception("Failed to fetch feed %s", feed.url)
            continue

        for rss_job in rss_jobs:
            async with AsyncSessionLocal() as session:
                job = await insert_job_if_new(session, feed.id, rss_job)
            if job is not None:
                new_count += 1
                await on_new_job(job)

    return new_count


async def run_forever(interval_seconds: int, on_new_job: OnNewJob) -> None:
    while True:
        try:
            new_count = await poll_once(on_new_job)
            logger.info("Poll cycle complete, %d new jobs", new_count)
        except Exception:
            logger.exception("Poll cycle failed")
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 2: Manual dedup verification against the live feed**

Requires a real Vollna feed URL seeded as a `feeds` row first (do this once, ad hoc, via psql against the running db from Task 3/2):

```bash
docker compose exec db psql -U upwork -d upwork -c \
  "INSERT INTO feeds (url, label, is_active) VALUES ('https://www.vollna.com/rss/jHnt1RqCeyZBPVko41Ly', 'main', true);"
```

Then run a small ad hoc script twice back-to-back:

```bash
uv run python -c "
import asyncio
from upwork_bot.rss.poller import poll_once

async def noop(job):
    print('new job:', job.external_pid, job.title)

print('run 1:', asyncio.run(poll_once(noop)))
"
uv run python -c "
import asyncio
from upwork_bot.rss.poller import poll_once

async def noop(job):
    print('new job:', job.external_pid, job.title)

print('run 2:', asyncio.run(poll_once(noop)))
"
```

Expected: run 1 reports N new jobs (N = however many are currently live in the feed), run 2 reports `0` — confirms dedup works against the real feed shape.

- [ ] **Step 3: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/rss/poller.py
git commit -m "feat: add asyncio RSS poller loop with per-feed error isolation"
```

---

## Task 6: aiogram Skeleton + Owner-Only Middleware + Feed Commands

**Files:**
- Create: `src/upwork_bot/bot/__init__.py`
- Create: `src/upwork_bot/bot/main.py`
- Create: `src/upwork_bot/bot/middlewares/__init__.py`
- Create: `src/upwork_bot/bot/middlewares/owner_only.py`
- Create: `src/upwork_bot/bot/handlers/__init__.py`
- Create: `src/upwork_bot/bot/handlers/feeds.py`
- Test: `tests/test_owner_only.py`

**Interfaces:**
- Produces: `bot.middlewares.owner_only.OwnerOnlyMiddleware` (aiogram `BaseMiddleware`, works for both `Message` and `CallbackQuery` events).
- Produces: `bot.handlers.feeds.router` (aiogram `Router`) with `/addfeed <url> <label>`, `/removefeed <id>`, `/listfeeds`.
- Produces: `bot.main.create_dispatcher() -> Dispatcher` wiring middleware + all routers (feeds router now, others added in later tasks by import).
- Consumes: `Settings.admin_telegram_id` from Task 1, `db.repo` CRUD helpers (add `add_feed`, `remove_feed`, `list_feeds` to `db/repo.py` in Step 3 below), `db.base.AsyncSessionLocal`.

- [ ] **Step 1: Write failing middleware test**

```python
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User

from upwork_bot.bot.middlewares.owner_only import OwnerOnlyMiddleware


def _make_message(user_id: int) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=user_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="x"),
    )


@pytest.mark.asyncio
async def test_owner_message_passes_through():
    middleware = OwnerOnlyMiddleware(admin_telegram_id=42)
    handler = AsyncMock(return_value="ok")

    result = await middleware(handler, _make_message(42), {})

    handler.assert_awaited_once()
    assert result == "ok"


@pytest.mark.asyncio
async def test_non_owner_message_is_blocked():
    middleware = OwnerOnlyMiddleware(admin_telegram_id=42)
    handler = AsyncMock(return_value="ok")

    result = await middleware(handler, _make_message(999), {})

    handler.assert_not_awaited()
    assert result is None
```

Run: `uv run pytest tests/test_owner_only.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'upwork_bot.bot'`

- [ ] **Step 2: Write bot/middlewares/owner_only.py**

```python
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class OwnerOnlyMiddleware(BaseMiddleware):
    def __init__(self, admin_telegram_id: int) -> None:
        self.admin_telegram_id = admin_telegram_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id != self.admin_telegram_id:
            return None
        return await handler(event, data)
```

- [ ] **Step 3: Run middleware test, verify pass**

Run: `uv run pytest tests/test_owner_only.py -v`
Expected: PASS

- [ ] **Step 4: Add feed CRUD to db/repo.py**

Append to `src/upwork_bot/db/repo.py`:

```python
async def add_feed(session, url: str, label: str) -> "Feed":
    from upwork_bot.db.models import Feed

    feed = Feed(url=url, label=label)
    session.add(feed)
    await session.commit()
    await session.refresh(feed)
    return feed


async def remove_feed(session, feed_id: int) -> bool:
    from upwork_bot.db.models import Feed

    feed = await session.get(Feed, feed_id)
    if feed is None:
        return False
    await session.delete(feed)
    await session.commit()
    return True


async def list_feeds(session) -> list["Feed"]:
    from upwork_bot.db.models import Feed
    from sqlalchemy import select

    result = await session.execute(select(Feed))
    return list(result.scalars())
```

(Move the two inline imports of `Feed`/`select` to the top of the file alongside the existing imports rather than inline — keep the file's imports consolidated.)

- [ ] **Step 5: Write bot/handlers/feeds.py**

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_feed, list_feeds, remove_feed

router = Router(name="feeds")


@router.message(Command("addfeed"))
async def cmd_addfeed(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /addfeed <rss_url> <label>")
        return

    _, url, label = parts
    async with AsyncSessionLocal() as session:
        feed = await add_feed(session, url=url, label=label)
    await message.answer(f"Added feed #{feed.id}: {feed.label}")


@router.message(Command("removefeed"))
async def cmd_removefeed(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /removefeed <id>")
        return

    feed_id = int(parts[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_feed(session, feed_id)
    await message.answer(f"Removed feed #{feed_id}" if removed else "No such feed")


@router.message(Command("listfeeds"))
async def cmd_listfeeds(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        feeds = await list_feeds(session)

    if not feeds:
        await message.answer("No feeds configured.")
        return

    lines = [f"#{f.id} [{'active' if f.is_active else 'paused'}] {f.label} — {f.url}" for f in feeds]
    await message.answer("\n".join(lines))
```

- [ ] **Step 6: Write bot/main.py**

```python
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from upwork_bot.bot.handlers import feeds
from upwork_bot.bot.middlewares.owner_only import OwnerOnlyMiddleware
from upwork_bot.config import get_settings


def create_dispatcher() -> Dispatcher:
    settings = get_settings()
    dispatcher = Dispatcher()

    owner_only = OwnerOnlyMiddleware(admin_telegram_id=settings.admin_telegram_id)
    dispatcher.message.middleware(owner_only)
    dispatcher.callback_query.middleware(owner_only)

    dispatcher.include_router(feeds.router)

    return dispatcher


def create_bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
```

- [ ] **Step 7: Manual verify — bot responds only to owner**

Run:
```bash
uv run python -c "
import asyncio
from upwork_bot.bot.main import create_bot, create_dispatcher

async def main():
    bot = create_bot()
    dp = create_dispatcher()
    await dp.start_polling(bot)

asyncio.run(main())
"
```
Send `/listfeeds` from the owner's Telegram account (the `ADMIN_TELEGRAM_ID` in `.env`) — expect a reply. Send `/listfeeds` from any other account — expect silence. Ctrl+C to stop.

- [ ] **Step 8: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot tests/test_owner_only.py src/upwork_bot/db/repo.py
git commit -m "feat: add aiogram skeleton, owner-only middleware, feed CRUD commands"
```

---

## Task 7: Analysis Chain Wired to Poller

**Files:**
- Create: `src/upwork_bot/llm/__init__.py`
- Create: `src/upwork_bot/llm/analysis_chain.py`
- Create: `src/upwork_bot/bot/handlers/jobs.py`
- Modify: `src/upwork_bot/db/repo.py` (add `get_active_resume`, `save_job_analysis`)
- Create: `src/upwork_bot/app.py`
- Test: `tests/test_analysis_chain.py`

**Interfaces:**
- Produces: `llm.analysis_chain.JobFit` pydantic model (`fit_score: int` 0-100, `short_summary: str`, `reasoning: str`) and `llm.analysis_chain.analyze_job(resume_text: str, job_title: str, job_description: str, categories: list[str]) -> JobFit` (async, uses LangChain `ChatOpenAI.with_structured_output(JobFit)`).
- Produces: `db.repo.get_active_resume(session) -> str | None`, `db.repo.save_job_analysis(session, job_id: int, fit: JobFit) -> None` (sets `status="analyzed"`).
- Produces: `bot.handlers.jobs.notify_new_job(bot: Bot, job: Job) -> None` — builds inline keyboard with `Generate proposal` (callback_data=`gen_proposal:{job.id}`) and `Open job` (`InlineKeyboardButton(url=job.upwork_link)`), sends to `settings.admin_telegram_id`.
- Produces: `app.py` `main()` that starts `bot.main.create_dispatcher()` polling and `rss.poller.run_forever` together via `asyncio.gather`, where the poller's `on_new_job` callback runs analysis then calls `notify_new_job`.
- Consumes: `rss.poller.run_forever` (Task 5), `bot.main.create_bot/create_dispatcher` (Task 6).

- [ ] **Step 1: Write failing analysis chain test (mocks the LLM call)**

```python
from unittest.mock import AsyncMock, patch

import pytest

from upwork_bot.llm.analysis_chain import JobFit, analyze_job


@pytest.mark.asyncio
async def test_analyze_job_returns_structured_fit():
    fake_fit = JobFit(fit_score=85, short_summary="Good Python fit", reasoning="Matches resume skills")

    with patch("upwork_bot.llm.analysis_chain._get_structured_llm") as mock_get_llm:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = fake_fit
        mock_get_llm.return_value = mock_chain

        result = await analyze_job(
            resume_text="Senior Python dev, 10 years, FastAPI, Django",
            job_title="Need Python developer",
            job_description="Build a scraper",
            categories=["Python"],
        )

    assert result.fit_score == 85
    assert result.short_summary == "Good Python fit"
```

Run: `uv run pytest tests/test_analysis_chain.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 2: Write llm/analysis_chain.py**

```python
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from upwork_bot.config import get_settings

ANALYSIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an assistant helping a freelancer triage Upwork job postings. "
            "Given the freelancer's resume and a job posting, score how well the job "
            "fits their skills (0-100), write a one-sentence summary, and explain your "
            "reasoning in 1-3 sentences.",
        ),
        (
            "human",
            "RESUME:\n{resume}\n\n"
            "JOB TITLE: {title}\n"
            "JOB CATEGORIES: {categories}\n"
            "JOB DESCRIPTION:\n{description}",
        ),
    ]
)


class JobFit(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    short_summary: str
    reasoning: str


@lru_cache
def _get_structured_llm():
    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0)
    return ANALYSIS_PROMPT | llm.with_structured_output(JobFit)


async def analyze_job(
    resume_text: str, job_title: str, job_description: str, categories: list[str]
) -> JobFit:
    chain = _get_structured_llm()
    return await chain.ainvoke(
        {
            "resume": resume_text,
            "title": job_title,
            "categories": ", ".join(categories),
            "description": job_description,
        }
    )
```

- [ ] **Step 3: Run test, verify pass**

Run: `uv run pytest tests/test_analysis_chain.py -v`
Expected: PASS

- [ ] **Step 4: Add resume/analysis repo helpers**

Append to `src/upwork_bot/db/repo.py`:

```python
async def get_active_resume(session) -> str | None:
    from sqlalchemy import select

    from upwork_bot.db.models import Resume

    result = await session.execute(select(Resume).order_by(Resume.updated_at.desc()).limit(1))
    resume = result.scalars().first()
    return resume.content if resume else None


async def save_job_analysis(session, job_id: int, fit) -> None:
    from upwork_bot.db.models import Job

    job = await session.get(Job, job_id)
    job.fit_score = fit.fit_score
    job.short_summary = fit.short_summary
    job.fit_reasoning = fit.reasoning
    job.status = "analyzed"
    await session.commit()
```

- [ ] **Step 5: Write bot/handlers/jobs.py**

```python
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from upwork_bot.config import get_settings
from upwork_bot.db.models import Job

router = Router(name="jobs")


def _job_keyboard(job_id: int, upwork_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Generate proposal", callback_data=f"gen_proposal:{job_id}"),
                InlineKeyboardButton(text="🔗 Open job", url=upwork_link),
            ]
        ]
    )


async def notify_new_job(bot: Bot, job: Job) -> None:
    settings = get_settings()
    text = (
        f"<b>{job.title}</b>\n\n"
        f"Fit score: {job.fit_score}/100\n"
        f"{job.short_summary}\n\n"
        f"<i>{job.fit_reasoning}</i>"
    )
    await bot.send_message(
        chat_id=settings.admin_telegram_id,
        text=text,
        reply_markup=_job_keyboard(job.id, job.upwork_link),
    )
```

(`gen_proposal:{job.id}` callback handler itself is added in Task 8's `proposals.py`; leave `router` here unused by commands for now — it exists so Task 8 can add callback handlers to the same router without touching this file again... actually simplest: this router stays empty of handlers in this task, `jobs.py` only exports `notify_new_job` + the keyboard builder. Do not register `router` in `bot/main.py` until Task 8 adds handlers to it.)

- [ ] **Step 6: Write app.py**

```python
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
```

- [ ] **Step 7: Manual verify against the live feed**

Ensure `.env` has a real `OPENAI_API_KEY` and a resume row exists (Task 8 adds `/setresume`; for now insert one directly):

```bash
docker compose exec db psql -U upwork -d upwork -c \
  "INSERT INTO resume (content) VALUES ('Senior Python developer, 8 years, FastAPI, Django, web scraping, automation.');"
```

Run:
```bash
uv run python -m upwork_bot.app
```
Wait for the next poll cycle (up to `POLL_INTERVAL_SECONDS`) with at least one new item live in the feed. Expected: a Telegram message arrives with title, fit_score, summary, reasoning, and both `Generate proposal` / `Open job` buttons, and tapping `Open job` opens the real `upwork.com/jobs/...` URL, not `vollna.com/go?...`.

- [ ] **Step 8: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/llm src/upwork_bot/bot/handlers/jobs.py src/upwork_bot/app.py src/upwork_bot/db/repo.py tests/test_analysis_chain.py
git commit -m "feat: wire LLM fit analysis into poller and push Telegram job cards"
```

---

## Task 8: Resume / Portfolio / Proposal-Example Ingestion + Embeddings

**Files:**
- Create: `src/upwork_bot/llm/embeddings.py`
- Create: `src/upwork_bot/bot/handlers/resume.py`
- Create: `src/upwork_bot/bot/handlers/portfolio.py`
- Create: `src/upwork_bot/bot/handlers/proposal_examples.py`
- Modify: `src/upwork_bot/db/repo.py` (add `upsert_resume`, `add_portfolio_project`, `add_proposal_example`)
- Modify: `src/upwork_bot/bot/main.py` (register the three new routers)

**Interfaces:**
- Produces: `llm.embeddings.embed_text(text: str) -> list[float]` (async, `OpenAIEmbeddings(model="text-embedding-3-small")`, returns 1536-length vector).
- Produces: `db.repo.upsert_resume(session, content: str) -> None`, `db.repo.add_portfolio_project(session, title, description, link, embedding) -> PortfolioProject`, `db.repo.add_proposal_example(session, source_text, embedding) -> ProposalExample`.
- Produces: handlers for `/setresume` (text arg or `.pdf`/`.docx` document upload), `/addproject <title> | <description> | <link>`, `/addexample` (text arg or document upload).
- Consumes: `pypdf`, `docx2txt` for document text extraction; `llm.embeddings.embed_text`.

- [ ] **Step 1: Write llm/embeddings.py**

```python
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from upwork_bot.config import get_settings


@lru_cache
def _get_embedder() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(model="text-embedding-3-small", api_key=settings.openai_api_key)


async def embed_text(text: str) -> list[float]:
    embedder = _get_embedder()
    return await embedder.aembed_query(text)
```

- [ ] **Step 2: Add ingestion repo helpers**

Append to `src/upwork_bot/db/repo.py`:

```python
async def upsert_resume(session, content: str) -> None:
    from upwork_bot.db.models import Resume

    resume = Resume(content=content)
    session.add(resume)
    await session.commit()


async def add_portfolio_project(session, title: str, description: str, link: str | None, embedding: list[float]):
    from upwork_bot.db.models import PortfolioProject

    project = PortfolioProject(title=title, description=description, link=link, embedding=embedding)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def add_proposal_example(session, source_text: str, embedding: list[float]):
    from upwork_bot.db.models import ProposalExample

    example = ProposalExample(source_text=source_text, embedding=embedding)
    session.add(example)
    await session.commit()
    await session.refresh(example)
    return example
```

(As in Task 6, consolidate these inline imports into the file's top-level import block when editing.)

- [ ] **Step 3: Write bot/handlers/resume.py**

```python
import io

import docx2txt
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from pypdf import PdfReader

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import upsert_resume

router = Router(name="resume")


def _extract_text(filename: str, data: bytes) -> str:
    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if filename.endswith(".docx"):
        return docx2txt.process(io.BytesIO(data))
    return data.decode("utf-8", errors="ignore")


@router.message(Command("setresume"))
async def cmd_setresume(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Send text after /setresume, or upload a .pdf/.docx as the next message.")
        return

    async with AsyncSessionLocal() as session:
        await upsert_resume(session, content=parts[1])
    await message.answer("Resume updated.")


@router.message(lambda message: message.document is not None)
async def handle_resume_document(message: Message) -> None:
    document = message.document
    if not document.file_name or not document.file_name.endswith((".pdf", ".docx")):
        return

    file = await message.bot.get_file(document.file_id)
    buffer = await message.bot.download_file(file.file_path)
    text = _extract_text(document.file_name, buffer.read())

    async with AsyncSessionLocal() as session:
        await upsert_resume(session, content=text)
    await message.answer("Resume updated from uploaded document.")
```

- [ ] **Step 4: Write bot/handlers/portfolio.py**

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_portfolio_project
from upwork_bot.llm.embeddings import embed_text

router = Router(name="portfolio")


@router.message(Command("addproject"))
async def cmd_addproject(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or "|" not in parts[1]:
        await message.answer("Usage: /addproject <title> | <description> | <link>")
        return

    fields = [f.strip() for f in parts[1].split("|")]
    if len(fields) < 2:
        await message.answer("Usage: /addproject <title> | <description> | <link>")
        return

    title, description = fields[0], fields[1]
    link = fields[2] if len(fields) > 2 else None

    embedding = await embed_text(f"{title}\n{description}")

    async with AsyncSessionLocal() as session:
        project = await add_portfolio_project(session, title, description, link, embedding)

    await message.answer(f"Added project #{project.id}: {project.title}")
```

- [ ] **Step 5: Write bot/handlers/proposal_examples.py**

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_proposal_example
from upwork_bot.llm.embeddings import embed_text

router = Router(name="proposal_examples")


@router.message(Command("addexample"))
async def cmd_addexample(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /addexample <text of a past proposal>")
        return

    source_text = parts[1]
    embedding = await embed_text(source_text)

    async with AsyncSessionLocal() as session:
        example = await add_proposal_example(session, source_text, embedding)

    await message.answer(f"Added proposal example #{example.id}")
```

- [ ] **Step 6: Register new routers in bot/main.py**

Modify `src/upwork_bot/bot/main.py`:

```python
from upwork_bot.bot.handlers import feeds, portfolio, proposal_examples, resume
```

and in `create_dispatcher()`:

```python
    dispatcher.include_router(feeds.router)
    dispatcher.include_router(resume.router)
    dispatcher.include_router(portfolio.router)
    dispatcher.include_router(proposal_examples.router)
```

- [ ] **Step 7: Manual verify**

Run the bot (`uv run python -m upwork_bot.app`), from owner Telegram account send:
- `/setresume Senior Python dev with 8 years experience...` → expect "Resume updated."
- `/addproject Scraper Bot | Built a resilient scraping pipeline | https://github.com/example/scraper` → expect "Added project #1: Scraper Bot"
- `/addexample Hi, I read your job post and...` → expect "Added proposal example #1"

Verify rows landed with non-null embeddings:
```bash
docker compose exec db psql -U upwork -d upwork -c \
  "SELECT id, title FROM portfolio_projects; SELECT id FROM proposal_examples;"
```

- [ ] **Step 8: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/llm/embeddings.py src/upwork_bot/bot/handlers/resume.py src/upwork_bot/bot/handlers/portfolio.py src/upwork_bot/bot/handlers/proposal_examples.py src/upwork_bot/bot/main.py src/upwork_bot/db/repo.py
git commit -m "feat: add resume/portfolio/proposal-example ingestion with embeddings"
```

---

## Task 9: Proposal Generation Chain (RAG)

**Files:**
- Create: `src/upwork_bot/llm/proposal_chain.py`
- Modify: `src/upwork_bot/db/repo.py` (add `search_similar_portfolio`, `search_similar_examples`, `save_proposal`, `get_job`, `get_latest_proposal`)
- Modify: `src/upwork_bot/bot/handlers/jobs.py` (register `router` with the `gen_proposal:{id}` callback — this is where it gets wired into `bot/main.py`)
- Modify: `src/upwork_bot/bot/main.py` (register `jobs.router`)
- Test: `tests/test_proposal_chain.py`

**Interfaces:**
- Produces: `llm.proposal_chain.generate_proposal(resume_text, job_title, job_description, portfolio_snippets: list[str], example_snippets: list[str], previous_version: str | None = None, feedback: str | None = None) -> str` (async, `ChatOpenAI` plain text completion).
- Produces: `db.repo.search_similar_portfolio(session, embedding, top_k=3) -> list[PortfolioProject]`, `db.repo.search_similar_examples(session, embedding, top_k=3) -> list[ProposalExample]` (pgvector `<=>` cosine distance ordering via `sqlalchemy` `.order_by(PortfolioProject.embedding.cosine_distance(embedding))`).
- Produces: `db.repo.save_proposal(session, job_id, version, content, user_feedback=None) -> Proposal`, `db.repo.get_latest_proposal(session, job_id) -> Proposal | None`.
- Produces: `bot.handlers.jobs.router` callback handler for `gen_proposal:{job_id}` that runs the RAG pipeline and replies with the draft + `🔄 Regenerate with edits` button (`callback_data=f"regen_proposal:{job_id}"`).

- [ ] **Step 1: Write failing proposal chain test (mocks the LLM call)**

```python
from unittest.mock import AsyncMock, patch

import pytest

from upwork_bot.llm.proposal_chain import generate_proposal


@pytest.mark.asyncio
async def test_generate_proposal_calls_llm_with_context():
    with patch("upwork_bot.llm.proposal_chain._get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = "Dear client, I can help..."
        mock_get_llm.return_value = mock_llm

        result = await generate_proposal(
            resume_text="Python dev",
            job_title="Need scraper",
            job_description="Build a scraper",
            portfolio_snippets=["Scraper Bot: built a resilient pipeline"],
            example_snippets=["Hi, I read your post..."],
        )

    assert result == "Dear client, I can help..."
    mock_llm.ainvoke.assert_awaited_once()
```

Run: `uv run pytest tests/test_proposal_chain.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 2: Write llm/proposal_chain.py**

```python
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from upwork_bot.config import get_settings

PROPOSAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are helping a freelancer write an Upwork proposal. Use their resume, "
            "similar past portfolio projects, and past proposal examples as style/content "
            "reference. Write a concise, specific, non-generic proposal in the freelancer's "
            "voice. Do not use placeholder brackets.",
        ),
        (
            "human",
            "RESUME:\n{resume}\n\n"
            "JOB TITLE: {title}\n"
            "JOB DESCRIPTION:\n{description}\n\n"
            "RELEVANT PORTFOLIO PROJECTS:\n{portfolio}\n\n"
            "PAST PROPOSAL EXAMPLES (style reference):\n{examples}\n\n"
            "{revision_context}",
        ),
    ]
)


@lru_cache
def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key, temperature=0.7)


def _build_revision_context(previous_version: str | None, feedback: str | None) -> str:
    if not previous_version:
        return ""
    return (
        f"PREVIOUS DRAFT:\n{previous_version}\n\n"
        f"USER FEEDBACK ON PREVIOUS DRAFT:\n{feedback}\n\n"
        "Revise the draft to address this feedback."
    )


async def generate_proposal(
    resume_text: str,
    job_title: str,
    job_description: str,
    portfolio_snippets: list[str],
    example_snippets: list[str],
    previous_version: str | None = None,
    feedback: str | None = None,
) -> str:
    llm = _get_llm()
    messages = PROPOSAL_PROMPT.format_messages(
        resume=resume_text,
        title=job_title,
        description=job_description,
        portfolio="\n---\n".join(portfolio_snippets) or "(none)",
        examples="\n---\n".join(example_snippets) or "(none)",
        revision_context=_build_revision_context(previous_version, feedback),
    )
    response = await llm.ainvoke(messages)
    return response.content
```

- [ ] **Step 3: Run test, verify pass**

Run: `uv run pytest tests/test_proposal_chain.py -v`
Expected: PASS

- [ ] **Step 4: Add pgvector search + proposal repo helpers**

Append to `src/upwork_bot/db/repo.py`:

```python
async def search_similar_portfolio(session, embedding: list[float], top_k: int = 3):
    from sqlalchemy import select

    from upwork_bot.db.models import PortfolioProject

    stmt = (
        select(PortfolioProject)
        .order_by(PortfolioProject.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def search_similar_examples(session, embedding: list[float], top_k: int = 3):
    from sqlalchemy import select

    from upwork_bot.db.models import ProposalExample

    stmt = (
        select(ProposalExample)
        .order_by(ProposalExample.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def get_job(session, job_id: int):
    from upwork_bot.db.models import Job

    return await session.get(Job, job_id)


async def get_latest_proposal(session, job_id: int):
    from sqlalchemy import select

    from upwork_bot.db.models import Proposal

    stmt = (
        select(Proposal)
        .where(Proposal.job_id == job_id)
        .order_by(Proposal.version.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def save_proposal(session, job_id: int, version: int, content: str, user_feedback: str | None = None):
    from upwork_bot.db.models import Proposal

    proposal = Proposal(job_id=job_id, version=version, content=content, user_feedback=user_feedback)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return proposal
```

- [ ] **Step 5: Rewrite bot/handlers/jobs.py to add the generate-proposal callback**

Replace the full contents of `src/upwork_bot/bot/handlers/jobs.py` with:

```python
from aiogram import Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from upwork_bot.config import get_settings
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Job
from upwork_bot.db.repo import (
    get_active_resume,
    get_job,
    save_proposal,
    search_similar_examples,
    search_similar_portfolio,
)
from upwork_bot.llm.embeddings import embed_text
from upwork_bot.llm.proposal_chain import generate_proposal

router = Router(name="jobs")


def _job_keyboard(job_id: int, upwork_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Generate proposal", callback_data=f"gen_proposal:{job_id}"),
                InlineKeyboardButton(text="🔗 Open job", url=upwork_link),
            ]
        ]
    )


def _regenerate_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔄 Regenerate with edits", callback_data=f"regen_proposal:{job_id}")]]
    )


async def notify_new_job(bot: Bot, job: Job) -> None:
    settings = get_settings()
    text = (
        f"<b>{job.title}</b>\n\n"
        f"Fit score: {job.fit_score}/100\n"
        f"{job.short_summary}\n\n"
        f"<i>{job.fit_reasoning}</i>"
    )
    await bot.send_message(
        chat_id=settings.admin_telegram_id,
        text=text,
        reply_markup=_job_keyboard(job.id, job.upwork_link),
    )


@router.callback_query(lambda c: c.data.startswith("gen_proposal:"))
async def handle_generate_proposal(callback: CallbackQuery) -> None:
    job_id = int(callback.data.split(":", 1)[1])
    await callback.answer("Generating proposal...")

    async with AsyncSessionLocal() as session:
        job = await get_job(session, job_id)
        resume_text = await get_active_resume(session) or ""
        embedding = await embed_text(job.description)
        portfolio = await search_similar_portfolio(session, embedding)
        examples = await search_similar_examples(session, embedding)

        content = await generate_proposal(
            resume_text=resume_text,
            job_title=job.title,
            job_description=job.description,
            portfolio_snippets=[f"{p.title}: {p.description}" for p in portfolio],
            example_snippets=[e.source_text for e in examples],
        )

        await save_proposal(session, job_id=job.id, version=1, content=content)

    await callback.message.answer(content, reply_markup=_regenerate_keyboard(job_id))
```

- [ ] **Step 6: Register jobs.router in bot/main.py**

Modify `src/upwork_bot/bot/main.py` imports:

```python
from upwork_bot.bot.handlers import feeds, jobs, portfolio, proposal_examples, resume
```

and add:

```python
    dispatcher.include_router(jobs.router)
```

Also update `src/upwork_bot/app.py`'s import of `notify_new_job` — it already imports from `upwork_bot.bot.handlers.jobs`, which is unchanged (function still exists), so no further edit needed there.

- [ ] **Step 7: Manual verify RAG quality**

With the resume + at least one `portfolio_projects` row + one `proposal_examples` row seeded from Task 8, trigger `/listfeeds` or wait for a new job push, tap **Generate proposal**. Expected: draft text references the seeded portfolio project or mirrors the tone of the seeded example, is not generic boilerplate, and a `🔄 Regenerate with edits` button appears below it.

- [ ] **Step 8: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/llm/proposal_chain.py src/upwork_bot/bot/handlers/jobs.py src/upwork_bot/bot/main.py src/upwork_bot/db/repo.py tests/test_proposal_chain.py
git commit -m "feat: add RAG proposal generation over portfolio and proposal examples"
```

---

## Task 10: Regenerate-with-Feedback FSM Flow

**Files:**
- Create: `src/upwork_bot/bot/handlers/proposals.py`
- Modify: `src/upwork_bot/bot/handlers/jobs.py` (remove regenerate callback stub if any conflicts — none exist yet, this task owns `regen_proposal:*`)
- Modify: `src/upwork_bot/bot/main.py` (register `proposals.router`)

**Interfaces:**
- Produces: `bot.handlers.proposals.ProposalFeedbackStates` (aiogram `StatesGroup` with `waiting_for_feedback` state).
- Produces: `bot.handlers.proposals.router` with:
  - `regen_proposal:{job_id}` callback → sets FSM state, stores `job_id` in FSM data, prompts "Send your corrections as a message."
  - a state-scoped message handler (only fires while in `waiting_for_feedback`) that reruns `generate_proposal` with `previous_version` + `feedback`, saves as `version = latest.version + 1`, replies with the same `🔄 Regenerate with edits` button, and clears state back to none (loop-ready: user can tap regenerate again).
- Consumes: `llm.proposal_chain.generate_proposal`, `db.repo.get_latest_proposal/save_proposal/get_job/get_active_resume`, `llm.embeddings.embed_text`, `db.repo.search_similar_portfolio/search_similar_examples` (all from Task 9).

- [ ] **Step 1: Write bot/handlers/proposals.py**

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import (
    get_active_resume,
    get_job,
    get_latest_proposal,
    save_proposal,
    search_similar_examples,
    search_similar_portfolio,
)
from upwork_bot.llm.embeddings import embed_text
from upwork_bot.llm.proposal_chain import generate_proposal

router = Router(name="proposals")


class ProposalFeedbackStates(StatesGroup):
    waiting_for_feedback = State()


def _regenerate_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔄 Regenerate with edits", callback_data=f"regen_proposal:{job_id}")]]
    )


@router.callback_query(lambda c: c.data.startswith("regen_proposal:"))
async def handle_regen_request(callback: CallbackQuery, state: FSMContext) -> None:
    job_id = int(callback.data.split(":", 1)[1])
    await state.set_state(ProposalFeedbackStates.waiting_for_feedback)
    await state.update_data(job_id=job_id)
    await callback.answer()
    await callback.message.answer("Send your corrections as a message and I'll regenerate the draft.")


@router.message(ProposalFeedbackStates.waiting_for_feedback)
async def handle_feedback_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    job_id = data["job_id"]
    feedback = message.text or ""

    async with AsyncSessionLocal() as session:
        job = await get_job(session, job_id)
        latest = await get_latest_proposal(session, job_id)
        resume_text = await get_active_resume(session) or ""
        embedding = await embed_text(job.description)
        portfolio = await search_similar_portfolio(session, embedding)
        examples = await search_similar_examples(session, embedding)

        content = await generate_proposal(
            resume_text=resume_text,
            job_title=job.title,
            job_description=job.description,
            portfolio_snippets=[f"{p.title}: {p.description}" for p in portfolio],
            example_snippets=[e.source_text for e in examples],
            previous_version=latest.content if latest else None,
            feedback=feedback,
        )

        next_version = (latest.version + 1) if latest else 1
        await save_proposal(session, job_id=job_id, version=next_version, content=content, user_feedback=feedback)

    await state.clear()
    await message.answer(content, reply_markup=_regenerate_keyboard(job_id))
```

- [ ] **Step 2: Register proposals.router in bot/main.py**

Modify `src/upwork_bot/bot/main.py`:

```python
from upwork_bot.bot.handlers import feeds, jobs, portfolio, proposal_examples, proposals, resume
```

and add (after `jobs.router`, before other routers so its state-scoped message handler doesn't get shadowed by any catch-all — order matters in aiogram routing):

```python
    dispatcher.include_router(jobs.router)
    dispatcher.include_router(proposals.router)
```

Also add `storage=MemoryStorage()` to the `Dispatcher()` construction so FSM state persists across updates within a single process:

```python
from aiogram.fsm.storage.memory import MemoryStorage
...
    dispatcher = Dispatcher(storage=MemoryStorage())
```

- [ ] **Step 3: Manual verify the full regenerate loop**

Run the bot, generate a proposal (Task 9 flow), tap **🔄 Regenerate with edits**, send a correction like "make it shorter and mention my scraper project by name." Expected: bot replies with a new draft that is visibly shorter and explicitly references the named project; tapping regenerate again and sending a second correction produces a third version reflecting both corrections (verify by checking `proposals` table has 3 rows with increasing `version` for that `job_id`):

```bash
docker compose exec db psql -U upwork -d upwork -c \
  "SELECT job_id, version, user_feedback FROM proposals ORDER BY job_id, version;"
```

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot/handlers/proposals.py src/upwork_bot/bot/main.py
git commit -m "feat: add regenerate-with-feedback FSM flow for proposal drafts"
```

---

## Task 11: Full docker-compose End-to-End Smoke Test

**Files:**
- Modify: `.env` (not committed — local only, ensure it's populated for this run)
- No new source files; this task only verifies the full stack via Docker.

**Interfaces:**
- Consumes: everything from Tasks 1-10.

- [ ] **Step 1: Ensure .env is complete**

Verify `.env` (git-ignored, local) has real `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `OPENAI_API_KEY`, and `DATABASE_URL=postgresql+asyncpg://upwork:upwork@db:5432/upwork` (note: `db` hostname, not `localhost`, since this now runs inside the compose network).

- [ ] **Step 2: Bring up the full stack**

Run:
```bash
docker compose down
docker compose up -d --build
docker compose logs -f bot
```
Expected: `db` becomes healthy, `bot` container starts without traceback, logs show `Poll cycle complete, N new jobs` on the configured interval.

- [ ] **Step 3: Apply migrations inside the compose network (first run only)**

Run:
```bash
docker compose run --rm bot uv run alembic upgrade head
```
Expected: migration `0001` applies cleanly against the `db` service.

- [ ] **Step 4: Full manual Telegram walkthrough**

- Receive a job push (or trigger via `/listfeeds` + wait for poll cycle) → tap **Generate proposal** → get draft with `🔄 Regenerate with edits` button.
- Send a correction message → confirm regenerated draft reflects it.
- Tap **Open job** → confirm it opens the real Upwork URL, not the Vollna redirect.
- Restart the `bot` container (`docker compose restart bot`) and confirm the poller does not re-push already-seen jobs (dedup survives restart because it's DB-backed, not in-memory).

- [ ] **Step 5: Final lint + full test suite pass**

Run:
```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -v
```
Expected: all checks and tests pass (DB-dependent tests require `docker compose up -d db` to still be running).

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "chore: verify full docker-compose stack end-to-end"
```

---

## Self-Review Notes

- Spec coverage: RSS shape/dedup (Task 4), polling cadence (Task 5), Postgres+pgvector schema (Task 3), owner-only gating (Task 6), analysis+push with correct link decoding (Task 7), ingestion+embeddings (Task 8), RAG proposal generation (Task 9), regenerate FSM (Task 10), docker-compose end-to-end (Task 11) — all ten build-order items from the spec map to a task.
- Naming consistency checked: `generate_proposal(..., previous_version=None, feedback=None)` signature from Task 9 matches the call in Task 10's `handle_feedback_message`; `save_proposal(session, job_id, version, content, user_feedback=None)` matches both call sites; `JobFit` fields (`fit_score`, `short_summary`, `reasoning`) match `save_job_analysis` and `notify_new_job` usage.
- `jobs.py` is written once in Task 7 (notify-only) and then fully replaced in Task 9 Step 5 once the generate-proposal callback is needed — flagged explicitly in Task 9 so the executor doesn't hand-merge diffs.

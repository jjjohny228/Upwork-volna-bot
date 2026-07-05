# Upwork Job-Hunter Telegram Bot

Single-user Telegram bot that polls [Vollna](https://vollna.com) RSS feeds for Upwork job postings, stores every job in Postgres, scores fit against the owner's resume via LLM, pushes Telegram cards with action buttons, and generates/regenerates Upwork proposal drafts via RAG over the owner's resume, portfolio, and past proposals.

> **Status:** under active build-out. See [docs/superpowers/plans/2026-07-01-upwork-lead-bot.md](docs/superpowers/plans/2026-07-01-upwork-lead-bot.md) for the full implementation plan and current progress.

## Features

- **RSS polling** — checks one or more Vollna RSS feeds every `POLL_INTERVAL_SECONDS` (default 180s, must stay under Vollna's ~10 minute feed expiry), dedupes jobs by the stable `pid` parameter in the feed link.
- **Fit analysis** — every new job is scored against the owner's resume via an LLM (fit score 0-100, short summary, reasoning), then pushed to Telegram.
- **Proposal generation (RAG)** — retrieves the most relevant past portfolio projects and proposal examples via pgvector cosine similarity, then drafts a tailored Upwork proposal.
- **Iterative regeneration** — send free-text corrections and the bot regenerates the draft, folding in your feedback, looping as many times as needed.
- **Owner-only** — every command and callback is gated to a single Telegram user id.

## Stack

Python 3.12 · [uv](https://docs.astral.sh/uv/) · [aiogram](https://docs.aiogram.dev/) 3.x · SQLAlchemy 2.0 (async, asyncpg) · Alembic · Postgres + [pgvector](https://github.com/pgvector/pgvector) · [LangChain](https://python.langchain.com/) + `langchain-openai` (GPT for analysis/generation, `text-embedding-3-small` for embeddings) · Docker Compose · ruff

## Setup

1. Copy the env template and fill in real values:

   ```bash
   cp .env.example .env
   ```

   | Var | Purpose |
   |---|---|
   | `BOT_TOKEN` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
   | `ADMIN_TELEGRAM_ID` | your numeric Telegram user id — the only account the bot responds to |
   | `DATABASE_URL` | `postgresql+asyncpg://upwork:upwork@db:5432/upwork` for Docker, or `@localhost:5433/upwork` for local dev against `docker compose up -d db` |
   | `OPENAI_API_KEY` | OpenAI API key (analysis, proposal generation, embeddings) |
   | `POLL_INTERVAL_SECONDS` | RSS poll cadence in seconds (default `180`) |

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Bring up Postgres/pgvector and apply migrations:

   ```bash
   docker compose up -d db
   uv run alembic upgrade head
   ```

4. Run the bot locally:

   ```bash
   uv run python -m upwork_bot.app
   ```

   Or run the full stack (bot + db) in Docker:

   ```bash
   docker compose up -d --build
   ```

## Development

```bash
uv run pytest                             # full test suite (some tests need `docker compose up -d db`)
uv run pytest tests/test_config.py -v     # single test file
uv run ruff check .                       # lint
uv run ruff format --check .              # format check
```

## Bot commands

Send `/start` to open the admin menu — every action below is reachable from there (Feeds / Resume / Portfolio / Proposal examples), no command arguments needed:

| Section | Actions |
|---|---|
| 📋 Feeds | List feeds (with ✖️ delete), Add feed (URL → label) |
| 📄 Resume | View resume, Set resume (paste text or upload `.pdf`/`.docx`) |
| 💼 Portfolio | List projects (with ✖️ delete), Add project (title → description → link or Skip) |
| ✍️ Proposal examples | List examples (with ✖️ delete), Add example (paste text) |

New job pushes include **📝 Generate proposal** / **🔗 Open job** buttons; generated proposals include a **🔄 Regenerate with edits** button — tap it, send a correction message, and get a revised draft.

See [CLAUDE.md](CLAUDE.md) for architecture notes and invariants that matter when extending the codebase.

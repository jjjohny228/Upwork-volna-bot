# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Single-user Telegram bot ("Upwork Job-Hunter") that polls Vollna RSS feeds for Upwork job postings, stores every job in Postgres, scores fit against the owner's resume via LLM, pushes Telegram cards with action buttons, and generates/regenerates Upwork proposal drafts via RAG over the owner's resume/portfolio/past proposals.

The full implementation plan (all 11 build tasks, exact file contents, data model, core flows) lives at `docs/superpowers/plans/2026-07-01-upwork-lead-bot.md`. That plan is the source of truth for architecture decisions — read it before making structural changes. As of this writing only Task 1 (project scaffold) and Task 2 (docker-compose) are complete; most of the architecture described below (db, rss, llm, bot packages) does not exist in the tree yet and is being built task-by-task per that plan.

## Commands

Environment/deps are managed with **uv only** — never pip/poetry/conda.

```bash
uv sync                                   # install/update deps from pyproject.toml + uv.lock
uv add <package>                          # add a new dependency
uv run pytest                             # run full test suite
uv run pytest tests/test_config.py -v     # run a single test file
uv run pytest tests/test_config.py::test_settings_reads_from_env -v  # single test
uv run ruff check .                       # lint
uv run ruff format --check .              # format check (CI gate)
uv run ruff format .                      # auto-format
```

Docker (Postgres + pgvector, and eventually the bot):

```bash
docker compose up -d db                   # bring up just Postgres/pgvector for local dev
docker compose exec db psql -U upwork -d upwork -c "SELECT 1;"   # sanity check
docker compose up -d --build              # full stack (bot + db) once app.py exists
uv run alembic upgrade head                # apply migrations (once migrations/ exists)
```

Local Postgres is exposed on host port **5433** (not 5432) specifically to avoid clashing with any Postgres already running on the machine. From inside the compose network the bot reaches it as `db:5432`.

## Configuration

All settings load via `pydantic-settings` (`src/upwork_bot/config.py`, `Settings` class + `get_settings()` cached factory) from a `.env` file — never hardcode secrets. See `.env.example` for the required vars: `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `DATABASE_URL`, `OPENAI_API_KEY`, `POLL_INTERVAL_SECONDS` (default 180).

## Architecture (per the plan — see plan doc for full detail)

- **`src/upwork_bot/db/`** — SQLAlchemy 2.0 async ORM (asyncpg driver) + Alembic migrations. Models: `Feed`, `Job`, `Resume`, `PortfolioProject`, `ProposalExample`, `Proposal`. `PortfolioProject`/`ProposalExample` carry a pgvector `Vector(1536)` embedding column (dimension fixed to `text-embedding-3-small`'s output). `repo.py` holds all dedup-safe upserts and pgvector cosine-similarity queries — DB access is async everywhere, no sync psycopg2.
- **`src/upwork_bot/rss/`** — `client.py` fetches/parses one Vollna RSS feed; the item `link` is a Vollna redirect (`vollna.com/go?...&pid=<id>&url=<double-url-encoded-upwork-link>`) — dedup key is the `pid` query param, and the real Upwork URL requires decoding the `url` param twice. `poller.py` loops over active `feeds` rows on an asyncio timer (`POLL_INTERVAL_SECONDS`, must stay well under Vollna's ~10 minute feed expiry).
- **`src/upwork_bot/llm/`** — all OpenAI/LangChain calls live here so they're mockable in tests. `analysis_chain.py`: resume+job → structured `{fit_score, short_summary, reasoning}` via `ChatOpenAI.with_structured_output`. `proposal_chain.py`: RAG proposal generation/regeneration using pgvector-retrieved portfolio projects + past proposal examples. `embeddings.py`: `text-embedding-3-small` wrapper.
- **`src/upwork_bot/bot/`** — aiogram 3.x. `middlewares/owner_only.py` gates every handler by comparing the Telegram user id to `settings.admin_telegram_id` (single-user bot — every new handler must go through this). `handlers/` is one file per command group (`jobs`, `proposals`, `feeds`, `resume`, `portfolio`, `proposal_examples`), each exposing an aiogram `Router` wired up in `bot/main.py`.
- **`src/upwork_bot/app.py`** — single entrypoint; runs the aiogram polling dispatcher and the RSS poller loop together via `asyncio.gather`. This is what the Dockerfile's `CMD` runs (`uv run python -m upwork_bot.app`).

## Key invariants to preserve

- Dedup key is always the `pid` query param parsed from the Vollna `link` — never title/description.
- The Telegram "Open job" button must link to the fully-decoded real Upwork URL, never the raw `vollna.com/go?...` redirect.
- Every bot handler is owner-only; no feature should be reachable by any Telegram user other than `ADMIN_TELEGRAM_ID`.
- Embedding columns are `Vector(1536)` throughout — don't introduce a different embedding model/dimension without updating both the schema and the migration.
- No index-tuning beyond a plain `ivfflat` note in the migration comments — this is an MVP with a handful of rows, don't over-engineer index strategy.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Single-user Telegram bot ("Upwork Job-Hunter") that parses Vollna job-alert emails from Gmail (over IMAP) for Upwork job postings, stores every job in Postgres, scores fit against the owner's resume via LLM, pushes Telegram cards with action buttons, and generates/regenerates Upwork proposal drafts via RAG over the owner's resume/portfolio/past proposals.

Historical context: the original build plan at `docs/superpowers/plans/2026-07-01-upwork-lead-bot.md` used **Vollna RSS** as the job source. That approach was dropped — polling the RSS token throttled Vollna's own web dashboard — and replaced by the Gmail source. The current design is in `docs/superpowers/specs/2026-07-07-gmail-job-source-design.md`; read it before touching the job-ingestion path. The old plan doc is otherwise still useful for the db/llm/bot design, but the `rss/` package and `feeds` table it describes no longer exist.

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
docker compose up -d --build              # full stack (bot + db)
uv run alembic upgrade head                # apply migrations
```

Local Postgres is exposed on host port **5433** (not 5432) specifically to avoid clashing with any Postgres already running on the machine. From inside the compose network the bot reaches it as `db:5432`.

## Configuration

All settings load via `pydantic-settings` (`src/upwork_bot/config.py`, `Settings` class + `get_settings()` cached factory) from a `.env` file — never hardcode secrets. See `.env.example` for the vars: `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `DATABASE_URL`, `OPENAI_API_KEY`, `POLL_INTERVAL_SECONDS` (default 180). Gmail source: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (a Gmail App Password — needs 2FA + IMAP enabled), `VOLLNA_SENDER` (default `info@vollna.com`), `GMAIL_MAILBOX` (default `INBOX`), `GMAIL_IMAP_HOST` (default `imap.gmail.com`). Proposal tuning: `PROPOSAL_SIGNATURE_NAME`, `HOURLY_RATE`. The two Gmail creds default to empty strings so tests/config load without them; empty creds make the poller's IMAP login fail (logged, retried).

## Architecture (per the plan — see plan doc for full detail)

- **`src/upwork_bot/db/`** — SQLAlchemy 2.0 async ORM (asyncpg driver) + Alembic migrations. Models: `Job`, `Resume`, `PortfolioProject`, `ProposalExample`, `Proposal` (there is no `Feed` model — the job source is Gmail, not per-feed RSS). `Job` carries `rate` and `ai_qualified` (parsed from the Vollna email) plus the fit fields (`fit_score`, `short_summary`, `fit_reasoning`, `skill_gaps`). `Resume` carries `pdf_bytes` (uploaded/generated resume PDF). `PortfolioProject`/`ProposalExample` carry a pgvector `Vector(1536)` embedding column (dimension fixed to `text-embedding-3-small`'s output). `repo.py` holds all dedup-safe upserts and pgvector cosine-similarity queries — DB access is async everywhere, no sync psycopg2. Migrations are hand-written with sequential integer revision ids (`0001`…`0005`), not `--autogenerate`.
- **`src/upwork_bot/gmail/`** — the job source. `client.py`: connects to Gmail over IMAP, `SEARCH UNSEEN FROM <VOLLNA_SENDER>`, parses each Vollna job-alert email into a `JobEmail` (BeautifulSoup over the quoted-printable `text/html` body), marks it `\Seen`. The dedup `pid` and the real Upwork URL are regex'd out of the awstrack/`vollna.com/go?...&pid=<id>&url=...` tracking link embedded in the email; title comes from the `New Job: <title>` Subject. `poller.py`: `run_forever` loops on `POLL_INTERVAL_SECONDS`, runs the blocking IMAP fetch via `asyncio.to_thread`, dedups by `pid`, calls `on_new_job`.
- **`src/upwork_bot/llm/`** — all OpenAI/LangChain calls live here so they're mockable in tests. `analysis_chain.py`: resume+job → structured `JobFit {fit_score, short_summary, reasoning, skill_gaps, required/matching/missing_skills}` via `ChatOpenAI.with_structured_output`, scored against a rubric. `proposal_chain.py`: RAG proposal generation/regeneration using pgvector-retrieved portfolio projects + past proposal examples; binds the `estimate_budget` tool (from `estimator.py`) for hourly-rate budgets and runs output through `strip_markdown` (Telegram gets plain text). `embeddings.py`: `text-embedding-3-small` wrapper. `estimator.py`: budget-from-hourly-rate tool (21 working days/mo, 8h/day). `pdf_utils.py` (top-level): text↔PDF for resumes.
- **`src/upwork_bot/bot/`** — aiogram 3.x. `middlewares/owner_only.py` gates every handler by comparing the Telegram user id to `settings.admin_telegram_id` (single-user bot — every new handler must go through this). `handlers/` is one file per command group (`menu`, `jobs`, `proposals`, `resume`, `portfolio`, `proposal_examples`), each exposing an aiogram `Router` wired up in `bot/main.py`. There is no `feeds` handler — Vollna does the filtering now. The main menu offers Resume, Portfolio, Proposal examples, and Write proposal (ad-hoc proposal from a pasted description).
- **`src/upwork_bot/app.py`** — single entrypoint; runs the aiogram polling dispatcher and the Gmail poller loop together via `asyncio.gather`. This is what the Dockerfile's `CMD` runs (`uv run python -m upwork_bot.app`).

## Key invariants to preserve

- Dedup key is always the Vollna `pid` (parsed from the `pid=<id>` param in the email's tracking link) — never title/description.
- The Telegram "Open job" button must link to the real Upwork job URL (`https://www.upwork.com/jobs/~<id>`), never the raw awstrack/`vollna.com/go?...` redirect.
- Job ingestion is Gmail-only; there is no RSS `feeds` table or feeds menu. Vollna filters jobs upstream — don't reintroduce per-feed config.
- Every bot handler is owner-only; no feature should be reachable by any Telegram user other than `ADMIN_TELEGRAM_ID`.
- Embedding columns are `Vector(1536)` throughout — don't introduce a different embedding model/dimension without updating both the schema and the migration.
- No index-tuning beyond a plain `ivfflat` note in the migration comments — this is an MVP with a handful of rows, don't over-engineer index strategy.

# Upwork Job-Hunter Telegram Bot

A multi-user Telegram bot for Upwork freelancers. Each user connects their own Gmail
inbox (where [Vollna](https://vollna.com) sends job-alert emails), and the bot parses every
new job, scores it against a **per-user** analysis prompt via an LLM, pushes a Telegram
card, and — on demand — drafts a tailored Upwork proposal using RAG over that user's
resume, portfolio, and past proposals. A single admin manages who has access and can
download a full database backup.

> **Multi-user rework in progress.** See [todo.md](todo.md) for the phased plan and
> [docs/superpowers/specs/2026-07-07-gmail-job-source-design.md](docs/superpowers/specs/2026-07-07-gmail-job-source-design.md)
> for the Gmail source design.

---

## How it works

```
Vollna → job-alert email → each user's Gmail inbox
   → bot poller (per user, every POLL_INTERVAL_SECONDS)
   → parse job (title, rate, real Upwork link, dedup by Vollna pid)
   → LLM fit analysis with THAT user's analysis prompt
   → Telegram card (loud ping if qualified, silent if not)
   → [Generate proposal] → RAG over the user's resume/portfolio/examples → draft
```

- **Qualified** jobs arrive as a normal notification; **disqualified** jobs arrive silently
  so your phone doesn't buzz for every miss.
- Dedup is always the Vollna `pid` (per user) — never the title.
- The **Open job** button always points at the real `upwork.com/jobs/~…` URL.

## Features

- **Per-user Gmail source** — each user stores their own Gmail address + app password; the
  bot polls every inbox independently.
- **Per-user analysis prompt** — paste your own job-analysis system prompt, or let the bot
  write one for you from a description of your stack/experience (text or PDF).
- **Per-user RAG** — resume, portfolio projects, and past proposal examples are scoped to
  each user and retrieved via pgvector cosine similarity when drafting proposals.
- **Iterative regeneration** — reply with free-text corrections; the bot redrafts, looping
  as many times as you need.
- **Admin panel** — add/remove users by Telegram ID and download a full `pg_dump` backup.
- **Graceful quota handling** — when the shared OpenAI account runs out of tokens, you get
  a clear message instead of a silent failure, and the admin is notified.

## Stack

Python 3.12 · [uv](https://docs.astral.sh/uv/) · [aiogram](https://docs.aiogram.dev/) 3.x ·
SQLAlchemy 2.0 (async, asyncpg) · Alembic · Postgres + [pgvector](https://github.com/pgvector/pgvector) ·
[LangChain](https://python.langchain.com/) + `langchain-openai` (GPT for analysis/generation,
`text-embedding-3-small` for embeddings) · Docker Compose · ruff

---

## Setup (admin / self-hosting)

1. Copy the env template and fill in real values:

   ```bash
   cp .env.example .env
   ```

   | Var | Purpose |
   |---|---|
   | `BOT_TOKEN` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
   | `ADMIN_TELEGRAM_ID` | your numeric Telegram user id — the only account with admin powers |
   | `DATABASE_URL` | `postgresql+asyncpg://upwork:upwork@db:5432/upwork` in Docker, or `@localhost:5433/upwork` for local dev |
   | `OPENAI_API_KEY` | shared OpenAI key — pays for analysis, proposal generation, embeddings for all users |
   | `POLL_INTERVAL_SECONDS` | inbox poll cadence in seconds (default `180`) |
   | `VOLLNA_SENDER` | sender address Vollna mails from (default `info@vollna.com`) |
   | `GMAIL_IMAP_HOST` | IMAP host (default `imap.gmail.com`) |

   > Gmail credentials are **not** in `.env` — each user enters their own from inside the
   > bot (see "Per-user setup" below).

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Bring up Postgres/pgvector and apply migrations:

   ```bash
   docker compose up -d db
   uv run alembic upgrade head
   ```

4. Run the bot:

   ```bash
   uv run python -m upwork_bot.app          # local
   docker compose up -d --build             # full stack (bot + db)
   ```

<!-- SCREENSHOT: terminal showing the bot starting up ("Poll cycle complete, N new jobs").
     Capture your local `uv run python -m upwork_bot.app` output and save as
     docs/images/startup.png -->
![Bot startup](docs/images/startup.png)

---

## Admin guide

Open the bot and send `/start`. As the admin you see an extra **Admin** section.

- **Manage users** — add a user by pasting their numeric Telegram ID (or forwarding one of
  their messages), then activate/deactivate or remove them. Only listed, active users can
  use the bot.
- **Download DB** — the bot runs `pg_dump` and sends you the backup file. Restore it
  anywhere with `pg_restore` against a fresh Postgres.

<!-- SCREENSHOT: the admin menu with "Manage users" and "Download DB" buttons.
     Save as docs/images/admin-panel.png -->
![Admin panel](docs/images/admin-panel.png)

<!-- SCREENSHOT: the "Manage users" list showing one or two users with activate/remove
     buttons. Save as docs/images/manage-users.png -->
![Manage users](docs/images/manage-users.png)

### Restoring a backup

```bash
# new machine / fresh Postgres
createdb upwork
pg_restore --clean --if-exists -d upwork path/to/backup.dump
```

---

## Per-user setup

Once the admin has added your Telegram ID, send `/start` and work through these sections.

### 1. Connect your Gmail

Vollna emails you one message per matching job. Point the bot at that inbox:

1. In Gmail, enable 2FA and create an **App Password** (Google Account → Security → App
   passwords). IMAP must be enabled.
2. In the bot: **Email source → set address**, then **set app password**. Use **Test
   connection** to confirm.

<!-- SCREENSHOT: the "Email source" menu with address/app-password/test-connection buttons.
     Save as docs/images/email-source.png -->
![Email source](docs/images/email-source.png)

### 2. Set your analysis prompt

This is what decides whether a job is a fit for *you*.

- **Paste my own** — supply your own system prompt.
- **Generate from my experience** — paste a description of your stack and experience, or
  upload a PDF (résumé / capabilities doc), and the bot writes a tailored prompt for you.
- **View current** — see what's active.

<!-- SCREENSHOT: the "Analysis prompt" menu, and/or an example generated prompt.
     Save as docs/images/analysis-prompt.png -->
![Analysis prompt](docs/images/analysis-prompt.png)

### 3. Add your resume, portfolio, and proposal examples

These feed the proposal generator (RAG). All are scoped to you.

- **Resume** — paste text or upload a `.pdf` / `.docx`.
- **Portfolio** — add projects (title → description → optional link).
- **Proposal examples** — paste past proposals that worked; the bot learns your voice.

<!-- SCREENSHOT: the main menu showing Resume / Portfolio / Proposal examples sections.
     Save as docs/images/main-menu.png -->
![Main menu](docs/images/main-menu.png)

### 4. Receive jobs and draft proposals

New matching jobs arrive as cards. Tap **📝 Generate proposal** for a draft, then
**🔄 Regenerate with edits** and send a correction to refine it. Tap **🔗 Open job** to go
straight to the Upwork posting.

<!-- SCREENSHOT: a job card in Telegram with the Generate proposal / Open job buttons, and
     a generated proposal below it. Save as docs/images/job-card.png -->
![Job card](docs/images/job-card.png)

---

## Development

```bash
uv run pytest                             # full test suite (some tests need `docker compose up -d db`)
uv run pytest tests/test_config.py -v     # single test file
uv run ruff check .                       # lint
uv run ruff format --check .              # format check
```

## Adding the screenshots

Create a `docs/images/` folder and drop the PNGs named exactly as referenced above
(`startup.png`, `admin-panel.png`, `manage-users.png`, `email-source.png`,
`analysis-prompt.png`, `main-menu.png`, `job-card.png`). Each `<!-- SCREENSHOT: … -->`
comment tells you what to capture; delete the comments once the images are in place.

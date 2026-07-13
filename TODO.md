# TODO — Multi-user rework

Goal: turn the single-owner bot into a multi-user service. Each user brings their own
Gmail (Vollna alerts), their own resume / portfolio / proposal examples, and their own
job-analysis system prompt. One admin manages users and backups. One shared OpenAI key
pays for everything.

> Historical single-user build log lives in git history (`.git/sdd/progress.md`, commits
> up to Jul 2026). This file supersedes it and tracks the multi-user rework.

## Decisions (locked)

- **Job source:** each user stores their own Gmail address + app password; the poller
  loops over all active users and fetches each inbox independently.
- **Onboarding:** admin-only. Admin adds a user by Telegram ID from the admin panel
  (paste ID or forward one of their messages). No self-signup.
- **DB backup:** admin panel button runs `pg_dump` and sends the dump file over Telegram;
  restore anywhere with `pg_restore`.
- **OpenAI key:** one shared admin key (`OPENAI_API_KEY`). "Tokens finished" = the shared
  account's quota/billing error, surfaced to the user who triggered it and to the admin.

## Assumptions (chosen defaults — change here if wrong)

- Admin is identified by `ADMIN_TELEGRAM_ID` (env, unchanged) and is also a normal user
  (can have own Gmail/resume/jobs).
- Gmail app passwords are stored in the DB. MVP: stored as-is in the owner's private DB;
  encryption-at-rest is a noted follow-up, not in scope now.
- Removing a user *deactivates* them (keeps their data) by default; hard-delete is a
  separate explicit action.
- Per-user Gmail cursor (last-seen date/UID) lives on the `users` row so each inbox is
  polled independently without re-processing.
- `pg_dump` runs against `DATABASE_URL` in custom format (`-Fc`); the binary is available
  in the bot container (add to Dockerfile if missing).

---

## Phase 1 — Data model: users + per-user ownership

- [x] Add `User` model: `id`, `telegram_id` (unique), `display_name`, `gmail_address`,
      `gmail_app_password`, `analysis_prompt` (Text, nullable), `gmail_cursor`
      (last-seen date/UID, nullable), `is_active` (bool), `created_at`.
      Also `notify_qualified_only` (bool, per-user job-delivery mode).
- [x] Add `user_id` FK to `Job`, `Resume`, `PortfolioProject`, `ProposalExample`
      (and `Proposal` inherits scope via `Job`). Dedup key becomes `(user_id, external_pid)`.
- [x] Alembic migration `0008_multiuser`: create `users`, add `user_id` columns +
      indexes, backfill existing rows to the admin user, update the `external_pid` unique
      constraint to be per-user. (up/down verified on scratch DB)
- [~] Update `repo.py`: add user CRUD (`get_user`, `get_user_by_telegram_id`,
      `list_users`, `add_user`, `set_active`, `delete_user`, `get_or_create_admin_user`,
      `set_notify_qualified_only`) — DONE. Threading `user_id` into every read query
      (resume/portfolio/examples) is deferred to Phase 6; only `insert_job_if_new` dedup
      is per-user so far.
- [x] Tests: user CRUD, per-user dedup (same pid, two users → two jobs).

## Phase 2 — Auth: registered-user + admin gates

- [x] Replace `OwnerOnlyMiddleware` with `RegisteredUserMiddleware`: looks up the Telegram
      id in `users`, rejects unknown/inactive users with a friendly message, injects the
      `User` into handler `data`.
- [x] Add `AdminOnlyMiddleware` (created; attach to admin-panel routers in Phase 3).
- [x] Wire `RegisteredUserMiddleware` in `bot/main.py`; admin auto-provisioned on first run.
- [x] Tests: unknown user blocked, inactive user blocked, admin passes admin gate.

## Job delivery mode (per-user) — DONE

- [x] `Settings` menu → toggle **Send all jobs** ⇄ **Send only qualified**, persisted on
      `user.notify_qualified_only`.
- [x] `notify_new_job` resolves the owning user, sends to their chat, and drops
      disqualified jobs when they chose qualified-only. Tests cover both modes.

## Phase 3 — Admin panel

- [ ] Admin-only menu section (visible only to `ADMIN_TELEGRAM_ID`): **Download DB**,
      **Manage users**.
- [ ] **Download DB**: run `pg_dump -Fc` via `asyncio.to_thread`, send the file as a
      Telegram document (with size/timeout guard).
- [ ] **Manage users**: list users (active/inactive), **Add user** (paste Telegram ID or
      forward a message → capture id + name), **Deactivate/Activate**, **Delete** (confirm).
- [ ] Tests: admin sees panel, non-admin does not; add/deactivate/delete flow (mock bot).

## Phase 4 — Per-user Gmail source

- [ ] Menu section **Email source**: set Gmail address, set app password (delete message
      after capture for safety), show connection status, "Test connection" button.
- [ ] Rework `gmail/poller.py`: on each cycle, loop active users with creds, fetch each
      inbox in a thread, dedup per user, advance that user's cursor, call
      `on_new_job(user, job)`. One user's IMAP failure is logged and does not stop others.
- [ ] Surface IMAP login failure to that user ("Gmail connection failed — re-check
      address/app password") and to the admin.
- [ ] Tests: poller iterates multiple users, isolates per-user failures, per-user cursor.

## Phase 5 — Per-user analysis prompt

- [ ] Treat the current `analysis_chain.py` prompt as the **default template/example**.
- [ ] Menu section **Analysis prompt**: **View current**, **Paste my own**,
      **Generate from my experience**.
- [ ] "Generate from my experience": user pastes text **or** uploads a PDF (reuse
      `pdf_utils`) describing stack/experience → LLM writes a tailored analysis system
      prompt in the house format → save to `user.analysis_prompt`.
- [ ] `qualify_job` takes the user's prompt (fallback to default when unset).
- [ ] Tests: prompt generation from text and PDF (mock LLM), analysis uses per-user prompt.

## Phase 6 — Per-user resume / portfolio / proposal examples

- [ ] Scope resume, portfolio, and proposal-example handlers + RAG retrieval to the
      calling user's `user_id` (pgvector similarity filtered by user).
- [ ] Proposal generation pulls only that user's resume/portfolio/examples.
- [ ] Tests: two users' examples don't cross-contaminate retrieval.

## Phase 7 — OpenAI quota / token error handling

- [ ] Central wrapper around LLM calls catching `RateLimitError` / `insufficient_quota`.
- [ ] On quota error: reply to the triggering user ("AI is temporarily out of tokens —
      the admin has been notified") and DM the admin with the details.
- [ ] Tests: simulated quota error → user + admin notified, no unhandled traceback.

## Phase 8 — Docs & config

- [ ] Rewrite `README.md`: what it is, multi-user setup, admin guide, per-user guide,
      screenshot placeholders (done alongside this todo — keep in sync).
- [ ] Update `.env.example` and `config.py`: remove the single-account `GMAIL_*` vars that
      moved per-user; keep `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `DATABASE_URL`,
      `OPENAI_API_KEY`, `POLL_INTERVAL_SECONDS`, `VOLLNA_SENDER`, `GMAIL_IMAP_HOST`.
- [ ] Ensure `pg_dump`/`pg_restore` are in the bot Docker image.
- [ ] Update `CLAUDE.md` architecture notes for the multi-user model.

## Verification

- [ ] `uv run pytest` green, `uv run ruff check .` / `format --check` clean.
- [ ] Migration `0008` up/down verified on a scratch DB.
- [ ] Live smoke: two Telegram accounts, each with own Gmail, receive their own job cards;
      admin downloads a DB dump and restores it into a fresh Postgres.

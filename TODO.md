# Build TODO

Tracks execution of the plan at [docs/superpowers/plans/2026-07-01-upwork-lead-bot.md](docs/superpowers/plans/2026-07-01-upwork-lead-bot.md) via subagent-driven development (implementer + task reviewer per task, review loop until clean). Authoritative history lives in git log + `.git/sdd/progress.md`; this file is a human-readable mirror of the same state.

## Done

- [x] Task 1: Project scaffold (uv, pyproject, config.py) — `3ec99ea..0a029d8`
- [x] Task 2: docker-compose + pgvector Postgres — `0a029d8..9d3e538`
- [x] Task 3: DB models + first Alembic migration — `de8629d..4a970aa`
- [x] Task 4: RSS client + dedup repo functions — `4a970aa..5be7d84` (incl. malformed-item fix)
- [x] Task 5: RSS poller loop — `5be7d84..25a3507` (incl. tz-aware `pub_date` fix, verified against the real live Vollna feed)
- [x] Task 6: aiogram skeleton + owner-only middleware + feed commands — `25a3507..9600ef8` (live owner-vs-non-owner Telegram check deferred to Task 11's full walkthrough)
- [x] Task 7: Analysis chain wired to poller + Telegram push — `9600ef8..d6257df` (verified live: 11 real jobs analyzed via OpenAI, pushed to real Telegram) — reviewer pass in progress

## Remaining

- [ ] Task 8: Resume/portfolio/proposal-example ingestion + embeddings (`/setresume`, `/addproject`, `/addexample`, `llm/embeddings.py`)
- [ ] Task 9: Proposal generation RAG chain (`llm/proposal_chain.py`, pgvector similarity search, `gen_proposal` callback)
- [ ] Task 10: Regenerate-with-feedback FSM flow (`bot/handlers/proposals.py`, `waiting_for_feedback` state)
- [ ] Task 11: Full docker-compose end-to-end smoke test (full stack up, alembic in-container, full manual Telegram walkthrough incl. owner-gating check deferred from Task 6)

## Notes for resuming in a fresh context

- Read `.git/sdd/progress.md` first — it's the recovery map. Trust it and `git log --oneline` over any stale recollection.
- Task briefs/reports for completed tasks live in `.git/sdd/task-N-brief.md` / `task-N-report.md` (git-ignored, local to this checkout — regenerate a brief anytime with the plan's `task-brief` script if needed).
- `.env` (git-ignored) already has real `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `OPENAI_API_KEY`, and `DATABASE_URL` pointed at `localhost:5433` — real Telegram/OpenAI calls are expected and intended during verification, not something to avoid.
- Live dev db already has a real seeded `feeds` row (`id=6`, label `main`, the real Vollna feed) and a seeded `resume` row from Task 7's verification.

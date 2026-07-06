# Gmail job source — design

**Date:** 2026-07-07
**Status:** Approved

## Problem

Jobs are currently pulled from a Vollna RSS feed (`src/upwork_bot/rss/`). Polling
the RSS token throttles the Vollna web dashboard on the account's plan: after
5–7 minutes of polling, new jobs stop appearing in Vollna's own interface. This
is Vollna-side behaviour tying RSS consumption to the account and is not fixable
in our code.

Vollna also sends a **job-alert email per matching job**. Parsing Gmail instead
of polling RSS removes the RSS/dashboard conflict entirely and gives us richer
data (rate, Vollna's own AI qualification) that the RSS feed did not carry.

## Decision summary

- **Source:** Gmail over IMAP (app password). RSS removed completely.
- **Dedup:** unchanged invariant — the Vollna `pid` query param.
- **Feeds:** the `feeds` table and the bot's Feeds menu are removed. Vollna does
  the filtering now; we no longer own feed URLs.
- **Vollna AI qualification:** parse the `Qualified` flag, store it, show it on
  the card. Our own LLM fit analysis stays unchanged (it scores *my* skills;
  Vollna's flag is general job quality).
- **Client-quality block** (rank, spent, hires, rating, country) is **out of
  scope** for now — only the rate is extracted.
- `filter_name` and `ai_reason` are **not** parsed.

## Email format (from a real sample)

- `From: Vollna <info@vollna.com>` (envelope from `@mail.vollna.com`).
- `Subject: New Job: <title>`.
- Body is a **single `text/html` part**, `Content-Transfer-Encoding:
  quoted-printable`, charset utf-8. No `text/plain` alternative.
- One email = one job.
- Stable labelled markup inside:
  - Title link → `<a href="…awstrack…/L0/…vollna.com/go?…pid=74835640&url=…
    upwork.com/jobs/~022074164276058730392…">Title</a>`
  - `<strong>Hourly Rate:</strong> 25 - 47 USD` **or** `<strong>Fixed Price:</strong> …`
  - `<strong>Published:</strong> Jul 6, 2026 16:12`
  - `<strong>AI Qualification:</strong> <span>Qualified</span>`
  - Description in the overview `<p>` block (contains HTML entities like
    `&#039;`, `&amp;`).

## Parsing → `JobEmail`

Dataclass fields:

```
external_pid: str      # dedup key
title: str
description: str
upwork_link: str
rate: str | None
ai_qualified: bool
pub_date: datetime | None
```

Extraction:

1. Decode the message: `email.message_from_bytes` → the `text/html` part →
   `get_payload(decode=True)` (handles quoted-printable) → `.decode("utf-8")`.
2. `external_pid` ← regex `pid=(\d+)` on the decoded HTML.
3. `upwork_link` ← regex `~(\d{15,})` → `https://www.upwork.com/jobs/~<id>`.
4. `title` ← Subject header with the leading `New Job: ` stripped.
5. `rate` ← BeautifulSoup: the `<strong>` whose text is `Hourly Rate:` or
   `Fixed Price:`, take the following text up to `<br>`. `None` if absent.
6. `description` ← BeautifulSoup `get_text()` of the overview `<p>`, entities
   unescaped, whitespace collapsed.
7. `ai_qualified` ← `True` if a `Qualified` span follows the
   `AI Qualification:` label, else `False`.

New dependency: **`beautifulsoup4`** (regex alone is too messy for the
entity-laden description). Added via `uv add`.

If `pid` or the upwork link cannot be extracted, the message is logged and
skipped (mirrors the current RSS malformed-item handling).

## Components

New package `src/upwork_bot/gmail/` mirroring the removed `rss/`:

- **`client.py`** — `fetch_new_job_emails()`:
  - Connect to `GMAIL_IMAP_HOST` (default `imap.gmail.com`, SSL) with
    `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`.
  - Select `GMAIL_MAILBOX` (default `INBOX`).
  - `SEARCH (UNSEEN FROM "<VOLLNA_SENDER>")`.
  - Fetch each message, parse to `JobEmail`, mark `\Seen` after processing.
  - Return `list[JobEmail]`.
- **`poller.py`** — `poll_once(on_new_job)` and `run_forever(interval, on_new_job)`:
  - Fetch job emails, dedup via `insert_job_if_new` (by `pid`), call
    `on_new_job` for genuinely new jobs. Same shape as the current RSS poller.

## Data flow

```
Vollna → email (info@vollna.com) → Gmail INBOX
  → gmail.poller (every POLL_INTERVAL_SECONDS)
  → gmail.client: IMAP SEARCH UNSEEN FROM vollna → parse → JobEmail
  → insert_job_if_new (dedup by pid) → Postgres
  → LLM fit analysis (unchanged) → Telegram card (+Rate +Vollna AI)
  → 📝 Generate proposal (unchanged)
```

## Database (migration 0005)

- `jobs` **add** `rate TEXT NULL`, `ai_qualified BOOLEAN NULL`.
- `jobs` **drop** `feed_id` (and its FK).
- **drop** table `feeds`.

Existing rows keep their data; `feed_id` column is dropped. This is an MVP with
a handful of rows, no data migration needed.

## Idempotency / error handling

- `pid` dedup in the DB is the real idempotency guard.
- `\Seen` keeps the inbox tidy and searches fast. If the process crashes before
  marking a message seen, the next cycle re-parses it and the DB dedup drops it.
- IMAP connection failures are logged and retried next cycle (poller catches and
  continues, as the RSS poller does today).
- Malformed emails (missing `pid`/link) are logged and skipped.

## Removals

- `src/upwork_bot/rss/` (client + poller).
- `src/upwork_bot/bot/handlers/feeds.py` and its router registration.
- Feeds buttons in `keyboards.py`; `open_feeds_menu` in `menu.py`;
  `FeedStates` in `states.py`.
- `Feed` model; feeds repo functions (`get_active_feeds`, `add_feed`,
  `remove_feed`, `list_feeds`, and RSS-oriented `insert_job_if_new` feed_id
  argument).
- `app.py` runs the gmail poller instead of the RSS poller.
- Tests: `test_rss_client.py`, `test_poller.py`, `test_feeds_handlers.py`, and
  feeds assertions in `test_repo.py` / `test_keyboards.py`.

## Config (.env)

```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
VOLLNA_SENDER=info@vollna.com
GMAIL_MAILBOX=INBOX
GMAIL_IMAP_HOST=imap.gmail.com
```

`POLL_INTERVAL_SECONDS` is reused. RSS-specific vars are removed.

## Telegram card

Add two lines to the existing card:

- `Rate: <rate>` (omit if `None`)
- `Vollna AI: Qualified` / `Vollna AI: Not qualified`

Fit-score analysis, skill gaps, and the proposal flow are unchanged.

## Testing

- `test_gmail_client.py` — feed the real sample email (raw bytes) through the
  parser; assert `external_pid == "74835640"`, upwork link ends
  `~022074164276058730392`, title stripped of `New Job: `, `rate == "25 - 47 USD"`,
  `ai_qualified is True`, description contains "My Adam Preview".
- A Fixed-Price variant assert for the `Fixed Price:` label.
- `test_gmail_poller.py` — dedup: same `pid` twice yields one job (IMAP mocked).
- Remove RSS/feeds tests listed above.
```

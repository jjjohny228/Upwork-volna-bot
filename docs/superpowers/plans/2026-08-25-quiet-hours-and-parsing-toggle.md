# Quiet Hours + Parsing Start/Pause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each user per-user control over when the bot parses their Gmail job alerts — a daily quiet-hours window (in their timezone) plus a manual start/pause switch — so a deployed bot stops parsing (and spending LLM calls) while they sleep.

**Architecture:** Add scheduling columns to `User`. A pure `is_parsing_allowed(user, now_utc)` helper decides whether parsing may run. The poller consults it per mailbox and, when disallowed, advances the mailbox cursor without fetching — the existing `since`-cutoff path then drops any mail that arrived while suspended. Bot UI: a dynamic start/pause toggle on the main menu, and timezone + quiet-hours editors under Settings.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async (asyncpg), Alembic, aiogram 3.x, `zoneinfo` (stdlib), pytest/pytest-asyncio, uv.

## Global Constraints

- Env/deps managed with **uv only** — never pip/poetry/conda.
- DB access is **async everywhere** (asyncpg); no sync psycopg2.
- Migrations are **hand-written** with sequential integer revision ids; next is `0010`, `Revises: 0009`. No `--autogenerate`.
- Every bot handler is **owner-gated** by `RegisteredUserMiddleware`, which injects the resolved `User` into `data["user"]` — new handlers take a `user: User` param, no manual gating.
- Embedding columns stay `Vector(1536)` — untouched by this work.
- Lint/format gate: `uv run ruff check .` and `uv run ruff format --check .` must pass.
- Times (`quiet_start`/`quiet_end`) are naive `datetime.time`, interpreted in the user's IANA `timezone`. Timezone stored as an IANA name string (DST handled by `zoneinfo`).

---

### Task 1: User scheduling columns + migration 0010

**Files:**
- Modify: `src/upwork_bot/db/models.py` (imports + `User` class, lines 1-35)
- Create: `migrations/versions/0010_quiet_hours_and_parsing_toggle.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `User.timezone: str | None`, `User.parsing_active: bool`, `User.quiet_hours_enabled: bool`, `User.quiet_start: time | None`, `User.quiet_end: time | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
import datetime as _dt

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user


@pytest.mark.asyncio
async def test_user_scheduling_defaults_and_fields():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558100, display_name="sched")
    try:
        # Defaults preserve current behavior: parsing on, quiet off, no tz/window.
        assert user.parsing_active is True
        assert user.quiet_hours_enabled is False
        assert user.timezone is None
        assert user.quiet_start is None
        assert user.quiet_end is None

        async with AsyncSessionLocal() as session:
            reloaded = await session.get(type(user), user.id)
            reloaded.timezone = "Europe/Kyiv"
            reloaded.quiet_start = _dt.time(23, 0)
            reloaded.quiet_end = _dt.time(7, 0)
            reloaded.quiet_hours_enabled = True
            reloaded.parsing_active = False
            await session.commit()

        async with AsyncSessionLocal() as session:
            again = await session.get(type(user), user.id)
            assert again.timezone == "Europe/Kyiv"
            assert again.quiet_start == _dt.time(23, 0)
            assert again.quiet_end == _dt.time(7, 0)
            assert again.quiet_hours_enabled is True
            assert again.parsing_active is False
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558100)
```

Check the top of `tests/test_models.py` for an existing `import pytest`; add it only if missing.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::test_user_scheduling_defaults_and_fields -v`
Expected: FAIL — `AttributeError`/`sqlalchemy` error: `User` has no attribute `parsing_active` (or column does not exist).

- [ ] **Step 3: Add the columns to the model**

In `src/upwork_bot/db/models.py`, add `time` to the datetime import and `Time` to the sqlalchemy import:

```python
from datetime import datetime, time
```
```python
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
```

In `class User`, after the `notify_qualified_only` column (before `created_at`), add:

```python
    # Per-user parsing schedule. `parsing_active` is the manual start/pause switch;
    # quiet hours suspend parsing during a daily local-time window (needs timezone).
    parsing_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    quiet_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_end: Mapped[time | None] = mapped_column(Time, nullable=True)
```

- [ ] **Step 4: Write the migration**

Create `migrations/versions/0010_quiet_hours_and_parsing_toggle.py`:

```python
"""quiet hours + parsing start/pause: per-user scheduling columns

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25

Adds per-user parsing schedule to `users`: `parsing_active` (manual on/off),
`timezone` (IANA name), `quiet_hours_enabled`, and the local-time
`quiet_start`/`quiet_end` window. Defaults keep existing users parsing normally
with quiet hours off, so no backfill is needed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("parsing_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("users", sa.Column("timezone", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "quiet_hours_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column("users", sa.Column("quiet_start", sa.Time(), nullable=True))
    op.add_column("users", sa.Column("quiet_end", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "quiet_end")
    op.drop_column("users", "quiet_start")
    op.drop_column("users", "quiet_hours_enabled")
    op.drop_column("users", "timezone")
    op.drop_column("users", "parsing_active")
```

- [ ] **Step 5: Apply the migration**

Run: `uv run alembic upgrade head`
Expected: applies `0010`, no error. (Requires `docker compose up -d db` running.)

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py::test_user_scheduling_defaults_and_fields -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/upwork_bot/db/models.py migrations/versions/0010_quiet_hours_and_parsing_toggle.py tests/test_models.py
git commit -m "feat: add per-user parsing schedule columns + migration 0010"
```

---

### Task 2: Repo setters

**Files:**
- Modify: `src/upwork_bot/db/repo.py` (Users section, after `set_analysis_prompt`, ~line 122)
- Test: `tests/test_repo.py`

**Interfaces:**
- Consumes: `User` columns from Task 1; existing `get_user_by_telegram_id`.
- Produces:
  - `set_timezone(session, telegram_id: int, tz: str) -> bool`
  - `set_parsing_active(session, telegram_id: int, active: bool) -> bool`
  - `set_quiet_hours_enabled(session, telegram_id: int, enabled: bool) -> bool`
  - `set_quiet_window(session, telegram_id: int, start: time, end: time) -> bool`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repo.py`:

```python
import datetime as _dt


@pytest.mark.asyncio
async def test_scheduling_setters_update_row():
    from upwork_bot.db.repo import (
        set_parsing_active,
        set_quiet_hours_enabled,
        set_quiet_window,
        set_timezone,
    )

    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558200, display_name="setters")
    try:
        async with AsyncSessionLocal() as session:
            assert await set_timezone(session, 558200, "Europe/Kyiv") is True
            assert await set_parsing_active(session, 558200, False) is True
            assert await set_quiet_hours_enabled(session, 558200, True) is True
            assert (
                await set_quiet_window(session, 558200, _dt.time(23, 0), _dt.time(7, 0))
                is True
            )

        async with AsyncSessionLocal() as session:
            saved = await get_user_by_telegram_id(session, 558200)
            assert saved.timezone == "Europe/Kyiv"
            assert saved.parsing_active is False
            assert saved.quiet_hours_enabled is True
            assert saved.quiet_start == _dt.time(23, 0)
            assert saved.quiet_end == _dt.time(7, 0)

        # Unknown telegram_id returns False.
        async with AsyncSessionLocal() as session:
            assert await set_timezone(session, 111, "UTC") is False
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558200)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repo.py::test_scheduling_setters_update_row -v`
Expected: FAIL — `ImportError: cannot import name 'set_timezone'`.

- [ ] **Step 3: Add the setters**

Add `time` to the top-of-file imports of `src/upwork_bot/db/repo.py`:

```python
from datetime import time
```

After `set_analysis_prompt` (~line 122), add:

```python
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


async def set_quiet_hours_enabled(
    session: AsyncSession, telegram_id: int, enabled: bool
) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.quiet_hours_enabled = enabled
    await session.commit()
    return True


async def set_quiet_window(
    session: AsyncSession, telegram_id: int, start: time, end: time
) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.quiet_start = start
    user.quiet_end = end
    await session.commit()
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repo.py::test_scheduling_setters_update_row -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/upwork_bot/db/repo.py tests/test_repo.py
git commit -m "feat: repo setters for timezone, parsing toggle, quiet hours"
```

---

### Task 3: `is_parsing_allowed` scheduling helper

**Files:**
- Create: `src/upwork_bot/gmail/schedule.py`
- Test: `tests/test_schedule.py`

**Interfaces:**
- Consumes: `User` scheduling columns (Task 1).
- Produces: `is_parsing_allowed(user: User, now_utc: datetime) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schedule.py`:

```python
from datetime import UTC, datetime, time

from upwork_bot.db.models import User
from upwork_bot.gmail.schedule import is_parsing_allowed


def _user(**kw) -> User:
    defaults = dict(
        telegram_id=1,
        parsing_active=True,
        quiet_hours_enabled=False,
        timezone=None,
        quiet_start=None,
        quiet_end=None,
    )
    defaults.update(kw)
    return User(**defaults)


def _utc(h: int, m: int = 0) -> datetime:
    return datetime(2026, 8, 25, h, m, tzinfo=UTC)


def test_paused_user_never_parses():
    assert is_parsing_allowed(_user(parsing_active=False), _utc(12)) is False


def test_quiet_disabled_allows():
    assert is_parsing_allowed(_user(parsing_active=True), _utc(3)) is True


def test_missing_timezone_allows_even_if_enabled():
    u = _user(quiet_hours_enabled=True, quiet_start=time(0), quiet_end=time(23, 59))
    assert is_parsing_allowed(u, _utc(12)) is True


def test_same_day_window_blocks_inside():
    # Window 09:00-17:00 UTC; 12:00 UTC is inside -> blocked.
    u = _user(
        quiet_hours_enabled=True,
        timezone="UTC",
        quiet_start=time(9),
        quiet_end=time(17),
    )
    assert is_parsing_allowed(u, _utc(12)) is False
    assert is_parsing_allowed(u, _utc(8)) is True
    assert is_parsing_allowed(u, _utc(17)) is True  # end is exclusive


def test_midnight_wrap_window():
    # Window 23:00-07:00 UTC (wraps midnight).
    u = _user(
        quiet_hours_enabled=True,
        timezone="UTC",
        quiet_start=time(23),
        quiet_end=time(7),
    )
    assert is_parsing_allowed(u, _utc(2)) is False
    assert is_parsing_allowed(u, _utc(23, 30)) is False
    assert is_parsing_allowed(u, _utc(12)) is True


def test_timezone_conversion():
    # Local window 23:00-07:00 in Europe/Kyiv (UTC+3 in August).
    # 21:00 UTC == 00:00 Kyiv -> inside quiet.
    u = _user(
        quiet_hours_enabled=True,
        timezone="Europe/Kyiv",
        quiet_start=time(23),
        quiet_end=time(7),
    )
    assert is_parsing_allowed(u, _utc(21)) is False   # 00:00 local
    assert is_parsing_allowed(u, _utc(9)) is True      # 12:00 local


def test_equal_times_allow():
    u = _user(
        quiet_hours_enabled=True,
        timezone="UTC",
        quiet_start=time(9),
        quiet_end=time(9),
    )
    assert is_parsing_allowed(u, _utc(9)) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schedule.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'upwork_bot.gmail.schedule'`.

- [ ] **Step 3: Write the helper**

Create `src/upwork_bot/gmail/schedule.py`:

```python
"""Per-user parsing-schedule gate.

Pure decision function: given a user's manual pause switch and optional quiet-hours
window (a daily local-time range in the user's IANA timezone), decide whether the
poller may parse that user's mailboxes right now.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from upwork_bot.db.models import User


def is_parsing_allowed(user: User, now_utc: datetime) -> bool:
    if not user.parsing_active:
        return False
    if not (
        user.quiet_hours_enabled
        and user.timezone
        and user.quiet_start
        and user.quiet_end
    ):
        return True

    local = now_utc.astimezone(ZoneInfo(user.timezone)).time()
    start, end = user.quiet_start, user.quiet_end
    if start <= end:
        in_quiet = start <= local < end
    else:  # window wraps past midnight
        in_quiet = local >= start or local < end
    return not in_quiet
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schedule.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/upwork_bot/gmail/schedule.py tests/test_schedule.py
git commit -m "feat: is_parsing_allowed scheduling gate"
```

---

### Task 4: Poller gating (skip + cursor-advance when disallowed)

**Files:**
- Modify: `src/upwork_bot/gmail/poller.py` (`poll_once`, lines 26-69)
- Test: `tests/test_gmail_poller.py`

**Interfaces:**
- Consumes: `is_parsing_allowed` (Task 3); existing `list_active_mailboxes`, `list_users`, `set_mailbox_cursor`.
- Produces: gated `poll_once` — mailboxes whose owner is paused/quiet are skipped without fetching and their cursor advanced to poll_start.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gmail_poller.py`:

```python
@pytest.mark.asyncio
async def test_poll_once_skips_paused_owner_and_advances_cursor():
    from upwork_bot.db.repo import set_parsing_active

    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=556005, display_name="paused")
        await add_mailbox(session, user.id, address="paused@x.com", app_password="p")
        await set_parsing_active(session, 556005, False)

    fetched: list[str] = []
    seen: list[int] = []

    def fake_fetch(address, *args, **kwargs):
        fetched.append(address)
        return [_job_email("paused-pid")] if address == "paused@x.com" else []

    async def on_new_job(job: Job) -> None:
        seen.append(job.id)

    try:
        with patch("upwork_bot.gmail.poller.fetch_new_job_emails", side_effect=fake_fetch):
            count = await poll_once(on_new_job)

        assert "paused@x.com" not in fetched  # never contacted IMAP
        assert seen == []                       # nothing delivered
        assert count == 0
        async with AsyncSessionLocal() as session:
            mb = (
                await session.execute(select(Mailbox).where(Mailbox.user_id == user.id))
            ).scalar_one()
            assert mb.cursor is not None         # cursor advanced -> drops backlog
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=556005)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gmail_poller.py::test_poll_once_skips_paused_owner_and_advances_cursor -v`
Expected: FAIL — `paused@x.com` IS in `fetched` (poller still fetches), assertion error.

- [ ] **Step 3: Add gating to `poll_once`**

In `src/upwork_bot/gmail/poller.py`, update imports:

```python
from upwork_bot.db.repo import (
    insert_job_if_new,
    list_active_mailboxes,
    list_users,
    set_mailbox_cursor,
)
from upwork_bot.gmail.schedule import is_parsing_allowed
```

Replace the body of `poll_once` from the `async with AsyncSessionLocal() as session:` that loads mailboxes (line 35) through the `for mb in mailboxes:` loop header, so owners are loaded and each mailbox is gated:

```python
    async with AsyncSessionLocal() as session:
        mailboxes = await list_active_mailboxes(session)
        owners = {u.id: u for u in await list_users(session)}

    new_count = 0
    for mb in mailboxes:
        poll_start = datetime.now(tz=UTC)
        owner = owners.get(mb.user_id)
        if owner is None or not is_parsing_allowed(owner, poll_start):
            # Parsing suspended for this owner: advance the watermark without
            # fetching so mail that arrived while suspended is later dropped by
            # the `since` cutoff (never parsed, never delivered).
            async with AsyncSessionLocal() as session:
                await set_mailbox_cursor(session, mb.id, poll_start.isoformat())
            continue

        # A stale cursor from a previous run never drags the poll below the
        # startup watermark — each restart ignores the accumulated backlog.
        mb_since = max(_parse_cursor(mb.cursor, fallback), fallback)
        try:
```

Keep the rest of the loop (the `job_emails = await asyncio.to_thread(...)` fetch through the cursor-advance at the end) unchanged. Note the original `poll_start = datetime.now(tz=UTC)` line inside the loop is now set at the top of the loop — remove the old duplicate assignment that sat just before the `try:`.

- [ ] **Step 4: Run the new test + the existing poller tests**

Run: `uv run pytest tests/test_gmail_poller.py -v`
Expected: PASS — new test passes; the three existing poller tests still pass (active owners are allowed by default, so they fetch as before).

- [ ] **Step 5: Commit**

```bash
git add src/upwork_bot/gmail/poller.py tests/test_gmail_poller.py
git commit -m "feat: gate poller per-owner parsing schedule"
```

---

### Task 5: Keyboards + states

**Files:**
- Modify: `src/upwork_bot/bot/keyboards.py`
- Modify: `src/upwork_bot/bot/states.py`
- Test: `tests/test_keyboards.py`

**Interfaces:**
- Produces:
  - Label constants `BTN_START_PARSING`, `BTN_PAUSE_PARSING`, `BTN_QUIET_HOURS`, `BTN_TIMEZONE`, `BTN_QUIET_TOGGLE_ON`, `BTN_QUIET_TOGGLE_OFF`, `BTN_QUIET_SET_WINDOW`, `BTN_TZ_MANUAL`.
  - `main_menu_kb(parsing_active: bool = True) -> ReplyKeyboardMarkup` (now parameterized).
  - `settings_menu_kb(notify_qualified_only: bool)` — adds Quiet hours + Timezone buttons.
  - `quiet_hours_menu_kb(enabled: bool) -> ReplyKeyboardMarkup`.
  - `timezone_inline_kb() -> InlineKeyboardMarkup` (callback data `tz:<name>` and `tz_manual`).
  - `COMMON_TIMEZONES: list[str]`.
  - State groups `TimezoneStates.waiting_for_manual`, `QuietHoursStates.waiting_for_start`, `QuietHoursStates.waiting_for_end`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_keyboards.py` (and extend the imports at the top of the file to include the new names used below):

```python
def test_main_menu_toggle_label_reflects_state():
    from upwork_bot.bot.keyboards import (
        BTN_PAUSE_PARSING,
        BTN_START_PARSING,
        main_menu_kb,
    )

    active_labels = _flatten(main_menu_kb(parsing_active=True))
    assert BTN_PAUSE_PARSING in active_labels
    assert BTN_START_PARSING not in active_labels

    paused_labels = _flatten(main_menu_kb(parsing_active=False))
    assert BTN_START_PARSING in paused_labels
    assert BTN_PAUSE_PARSING not in paused_labels


def test_settings_menu_has_quiet_and_timezone():
    from upwork_bot.bot.keyboards import BTN_QUIET_HOURS, BTN_TIMEZONE, settings_menu_kb

    labels = _flatten(settings_menu_kb(notify_qualified_only=False))
    assert BTN_QUIET_HOURS in labels
    assert BTN_TIMEZONE in labels


def test_quiet_hours_menu_toggle_label():
    from upwork_bot.bot.keyboards import (
        BTN_QUIET_TOGGLE_OFF,
        BTN_QUIET_TOGGLE_ON,
        quiet_hours_menu_kb,
    )

    on_labels = _flatten(quiet_hours_menu_kb(enabled=True))
    assert BTN_QUIET_TOGGLE_OFF in on_labels   # can disable when enabled

    off_labels = _flatten(quiet_hours_menu_kb(enabled=False))
    assert BTN_QUIET_TOGGLE_ON in off_labels    # can enable when disabled


def test_timezone_inline_kb_encodes_zones():
    from upwork_bot.bot.keyboards import COMMON_TIMEZONES, timezone_inline_kb

    kb = timezone_inline_kb()
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert f"tz:{COMMON_TIMEZONES[0]}" in datas
    assert "tz_manual" in datas
```

Update the existing `test_main_menu_has_all_sections` to account for the new toggle button — replace its body with:

```python
def test_main_menu_has_all_sections():
    from upwork_bot.bot.keyboards import BTN_PAUSE_PARSING

    labels = _flatten(main_menu_kb())
    assert {
        BTN_RESUME,
        BTN_PORTFOLIO,
        BTN_EXAMPLES,
        BTN_WRITE_PROPOSAL,
        BTN_SETTINGS,
        BTN_SETUP,
    }.issubset(set(labels))
    # Default state is active -> shows the pause toggle.
    assert BTN_PAUSE_PARSING in labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_keyboards.py -v`
Expected: FAIL — `ImportError` for the new constants.

- [ ] **Step 3: Add label constants**

In `src/upwork_bot/bot/keyboards.py`, after the existing `BTN_*` constants (before `def main_menu_kb`), add:

```python
BTN_START_PARSING = "▶️ Start parsing"
BTN_PAUSE_PARSING = "⏸ Pause parsing"

BTN_QUIET_HOURS = "🌙 Quiet hours"
BTN_TIMEZONE = "🕒 Timezone"

BTN_QUIET_TOGGLE_ON = "🔔 Enable quiet hours"
BTN_QUIET_TOGGLE_OFF = "🔕 Disable quiet hours"
BTN_QUIET_SET_WINDOW = "🕐 Set window"

BTN_TZ_MANUAL = "✍️ Enter manually"

COMMON_TIMEZONES = [
    "Europe/Kyiv",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Moscow",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
    "UTC",
]
```

- [ ] **Step 4: Parameterize `main_menu_kb` and extend `settings_menu_kb`**

Replace `main_menu_kb`:

```python
def main_menu_kb(parsing_active: bool = True) -> ReplyKeyboardMarkup:
    toggle = BTN_PAUSE_PARSING if parsing_active else BTN_START_PARSING
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_RESUME), KeyboardButton(text=BTN_PORTFOLIO)],
            [KeyboardButton(text=BTN_EXAMPLES), KeyboardButton(text=BTN_WRITE_PROPOSAL)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_SETUP)],
            [KeyboardButton(text=toggle)],
        ],
        resize_keyboard=True,
    )
```

In `settings_menu_kb`, add a row with the two new buttons — insert `[KeyboardButton(text=BTN_QUIET_HOURS), KeyboardButton(text=BTN_TIMEZONE)]` immediately after the mailboxes/qualify row:

```python
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MAILBOXES), KeyboardButton(text=BTN_QUALIFY_PROMPT)],
            [KeyboardButton(text=BTN_HOURLY_RATE), KeyboardButton(text=BTN_SIGNATURE)],
            [KeyboardButton(text=BTN_QUIET_HOURS), KeyboardButton(text=BTN_TIMEZONE)],
            [KeyboardButton(text=all_label)],
            [KeyboardButton(text=qualified_label)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )
```

- [ ] **Step 5: Add the quiet-hours submenu + timezone inline keyboards**

After `settings_menu_kb`, add:

```python
def quiet_hours_menu_kb(enabled: bool) -> ReplyKeyboardMarkup:
    toggle = BTN_QUIET_TOGGLE_OFF if enabled else BTN_QUIET_TOGGLE_ON
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=toggle)],
            [KeyboardButton(text=BTN_QUIET_SET_WINDOW), KeyboardButton(text=BTN_TIMEZONE)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )
```

In the inline-keyboard section (near `skip_link_kb`), add:

```python
def timezone_inline_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=tz, callback_data=f"tz:{tz}")]
        for tz in COMMON_TIMEZONES
    ]
    rows.append([InlineKeyboardButton(text=BTN_TZ_MANUAL, callback_data="tz_manual")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 6: Add state groups**

Append to `src/upwork_bot/bot/states.py`:

```python
class TimezoneStates(StatesGroup):
    waiting_for_manual = State()


class QuietHoursStates(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_keyboards.py -v`
Expected: PASS (all, including the updated `test_main_menu_has_all_sections`).

- [ ] **Step 8: Commit**

```bash
git add src/upwork_bot/bot/keyboards.py src/upwork_bot/bot/states.py tests/test_keyboards.py
git commit -m "feat: keyboards + states for parsing toggle, quiet hours, timezone"
```

---

### Task 6: Main-menu Start/Pause handlers

**Files:**
- Modify: `src/upwork_bot/bot/handlers/menu.py`
- Modify: `src/upwork_bot/bot/handlers/setup.py` (line 56 — pass `parsing_active`)
- Test: `tests/test_menu_parsing_toggle.py` (create)

**Interfaces:**
- Consumes: `set_parsing_active` (Task 2); `main_menu_kb`, `BTN_START_PARSING`, `BTN_PAUSE_PARSING` (Task 5).
- Produces: two handlers that flip `user.parsing_active` and re-render the main menu.

- [ ] **Step 1: Write the failing test**

Create `tests/test_menu_parsing_toggle.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.handlers.menu import pause_parsing, start_parsing
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user, get_user_by_telegram_id


def _make_message() -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=TgUser(id=42, is_bot=False, first_name="owner"),
        text="⏸ Pause parsing",
    )


@pytest.mark.asyncio
async def test_pause_then_start_parsing():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558300, display_name="toggle")

    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await pause_parsing(_make_message(), state, user)
        assert user.parsing_active is False
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558300)).parsing_active is False

        with patch.object(Message, "answer", new_callable=AsyncMock):
            await start_parsing(_make_message(), state, user)
        assert user.parsing_active is True
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558300)).parsing_active is True
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558300)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_menu_parsing_toggle.py -v`
Expected: FAIL — `ImportError: cannot import name 'pause_parsing'`.

- [ ] **Step 3: Add the handlers**

In `src/upwork_bot/bot/handlers/menu.py`, extend the keyboards import to add `BTN_PAUSE_PARSING` and `BTN_START_PARSING`, and add `from upwork_bot.db.repo import set_notify_qualified_only, set_parsing_active`. Add the `User` import if not present (`from upwork_bot.db.models import User` — already imported). Then add:

```python
@router.message(lambda m: m.text == BTN_PAUSE_PARSING)
async def pause_parsing(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        await set_parsing_active(session, user.telegram_id, False)
    user.parsing_active = False
    await message.answer(
        "⏸ Parsing <b>paused</b>. Jobs that arrive while paused are skipped.",
        reply_markup=main_menu_kb(user.parsing_active),
    )


@router.message(lambda m: m.text == BTN_START_PARSING)
async def start_parsing(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        await set_parsing_active(session, user.telegram_id, True)
    user.parsing_active = True
    await message.answer(
        "▶️ Parsing <b>started</b>.",
        reply_markup=main_menu_kb(user.parsing_active),
    )
```

- [ ] **Step 4: Make main-menu renders reflect state**

In `menu.py`, update `cmd_start` and `go_back_to_main_menu` to take `user: User` and pass `parsing_active`:

```python
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer(
        "Welcome to the Upwork Job-Hunter admin menu. Choose a section:",
        reply_markup=main_menu_kb(user.parsing_active),
    )
```
```python
@router.message(lambda m: m.text == BTN_BACK)
async def go_back_to_main_menu(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb(user.parsing_active))
```

In `src/upwork_bot/bot/handlers/setup.py` line 56, change `reply_markup=main_menu_kb()` to `reply_markup=main_menu_kb(user.parsing_active)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_menu_parsing_toggle.py tests/test_keyboards.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/upwork_bot/bot/handlers/menu.py src/upwork_bot/bot/handlers/setup.py tests/test_menu_parsing_toggle.py
git commit -m "feat: main-menu start/pause parsing handlers"
```

---

### Task 7: Timezone handler

**Files:**
- Create: `src/upwork_bot/bot/handlers/timezone.py`
- Modify: `src/upwork_bot/bot/main.py` (register router)
- Test: `tests/test_timezone_handler.py`

**Interfaces:**
- Consumes: `set_timezone` (Task 2); `BTN_TIMEZONE`, `timezone_inline_kb`, `settings_menu_kb` (Task 5); `TimezoneStates` (Task 5).
- Produces: router `router` handling `BTN_TIMEZONE`, callback `tz:<name>`, callback `tz_manual`, and `TimezoneStates.waiting_for_manual` text; helper `set_user_timezone(telegram_id, name) -> bool` that validates the IANA name.

- [ ] **Step 1: Write the failing test**

Create `tests/test_timezone_handler.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.handlers.timezone import process_manual_timezone
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user, get_user_by_telegram_id


def _msg(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=TgUser(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_manual_timezone_valid_saves_and_clears():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558400, display_name="tz")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_manual_timezone(_msg("Europe/Kyiv"), state, user)
        state.clear.assert_awaited()
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558400)).timezone == "Europe/Kyiv"
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558400)


@pytest.mark.asyncio
async def test_manual_timezone_invalid_rejected():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558401, display_name="tz2")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_manual_timezone(_msg("Not/AZone"), state, user)
        # Invalid name -> stays in state, nothing saved.
        state.clear.assert_not_awaited()
        async with AsyncSessionLocal() as session:
            assert (await get_user_by_telegram_id(session, 558401)).timezone is None
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558401)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_timezone_handler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'upwork_bot.bot.handlers.timezone'`.

- [ ] **Step 3: Write the handler**

Create `src/upwork_bot/bot/handlers/timezone.py`:

```python
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_TIMEZONE,
    cancel_kb,
    settings_menu_kb,
    timezone_inline_kb,
)
from upwork_bot.bot.states import TimezoneStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import set_timezone

router = Router(name="timezone")


def _is_valid_tz(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


@router.message(lambda m: m.text == BTN_TIMEZONE)
async def open_timezone(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    current = user.timezone or "not set"
    await message.answer(
        f"Current timezone: <b>{current}</b>.\nPick one or enter it manually:",
        reply_markup=timezone_inline_kb(),
    )


@router.callback_query(F.data.startswith("tz:"))
async def pick_timezone(callback: CallbackQuery, user: User) -> None:
    name = callback.data.split(":", 1)[1]
    if not _is_valid_tz(name):
        await callback.answer("Invalid timezone.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        await set_timezone(session, user.telegram_id, name)
    user.timezone = name
    await callback.message.answer(
        f"✅ Timezone set to <b>{name}</b>.",
        reply_markup=settings_menu_kb(user.notify_qualified_only),
    )
    await callback.answer()


@router.callback_query(F.data == "tz_manual")
async def ask_manual_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TimezoneStates.waiting_for_manual)
    await callback.message.answer(
        "Send an IANA timezone name, e.g. <code>Europe/Kyiv</code>.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(TimezoneStates.waiting_for_manual)
async def process_manual_timezone(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=settings_menu_kb(user.notify_qualified_only)
        )
        return

    name = (message.text or "").strip()
    if not _is_valid_tz(name):
        await message.answer("Unknown timezone. Send an IANA name like Europe/Kyiv.")
        return

    async with AsyncSessionLocal() as session:
        await set_timezone(session, user.telegram_id, name)
    user.timezone = name
    await state.clear()
    await message.answer(
        f"✅ Timezone set to <b>{name}</b>.",
        reply_markup=settings_menu_kb(user.notify_qualified_only),
    )
```

- [ ] **Step 4: Register the router**

In `src/upwork_bot/bot/main.py`, add `timezone` to the handlers import and include it before `menu.router`:

```python
from upwork_bot.bot.handlers import (
    jobs,
    mailboxes,
    menu,
    portfolio,
    proposal_examples,
    proposals,
    qualify_prompt,
    resume,
    setup,
    timezone,
    user_settings,
)
```
```python
    dispatcher.include_router(timezone.router)
    dispatcher.include_router(setup.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_timezone_handler.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add src/upwork_bot/bot/handlers/timezone.py src/upwork_bot/bot/main.py tests/test_timezone_handler.py
git commit -m "feat: timezone selection handler (inline list + manual entry)"
```

---

### Task 8: Quiet-hours handler

**Files:**
- Create: `src/upwork_bot/bot/handlers/quiet_hours.py`
- Modify: `src/upwork_bot/bot/main.py` (register router)
- Test: `tests/test_quiet_hours_handler.py`

**Interfaces:**
- Consumes: `set_quiet_hours_enabled`, `set_quiet_window` (Task 2); `BTN_QUIET_HOURS`, `BTN_QUIET_TOGGLE_ON`, `BTN_QUIET_TOGGLE_OFF`, `BTN_QUIET_SET_WINDOW`, `quiet_hours_menu_kb`, `settings_menu_kb` (Task 5); `QuietHoursStates` (Task 5).
- Produces: router handling the quiet-hours submenu, the enable/disable toggle (blocked without a timezone), and the two-step window FSM. Helper `_parse_hhmm(text) -> time | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_quiet_hours_handler.py`:

```python
import datetime as _dt
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from upwork_bot.bot.handlers.quiet_hours import (
    process_end,
    process_start,
    toggle_quiet_hours,
)
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_user, delete_user, get_user_by_telegram_id, set_timezone


def _msg(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=TgUser(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_enable_blocked_without_timezone():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558500, display_name="qh")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await toggle_quiet_hours(_msg("🔔 Enable quiet hours"), state, user)
        # No tz -> refuse to enable.
        assert user.quiet_hours_enabled is False
        async with AsyncSessionLocal() as session:
            assert (
                await get_user_by_telegram_id(session, 558500)
            ).quiet_hours_enabled is False
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558500)


@pytest.mark.asyncio
async def test_enable_with_timezone_succeeds():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558501, display_name="qh2")
        await set_timezone(session, 558501, "UTC")
        user.timezone = "UTC"
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await toggle_quiet_hours(_msg("🔔 Enable quiet hours"), state, user)
        assert user.quiet_hours_enabled is True
        async with AsyncSessionLocal() as session:
            assert (
                await get_user_by_telegram_id(session, 558501)
            ).quiet_hours_enabled is True
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558501)


@pytest.mark.asyncio
async def test_set_window_valid_two_steps():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558502, display_name="qh3")
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"quiet_start": "23:00"})
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_start(_msg("23:00"), state, user)
            state.update_data.assert_awaited_with(quiet_start="23:00")
            await process_end(_msg("07:00"), state, user)
        async with AsyncSessionLocal() as session:
            saved = await get_user_by_telegram_id(session, 558502)
            assert saved.quiet_start == _dt.time(23, 0)
            assert saved.quiet_end == _dt.time(7, 0)
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558502)


@pytest.mark.asyncio
async def test_set_window_rejects_bad_start():
    async with AsyncSessionLocal() as session:
        user = await add_user(session, telegram_id=558503, display_name="qh4")
    state = AsyncMock(spec=FSMContext)
    try:
        with patch.object(Message, "answer", new_callable=AsyncMock):
            await process_start(_msg("25:99"), state, user)
        # Bad time -> stays waiting, no data stored.
        state.update_data.assert_not_awaited()
    finally:
        async with AsyncSessionLocal() as session:
            await delete_user(session, telegram_id=558503)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_quiet_hours_handler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'upwork_bot.bot.handlers.quiet_hours'`.

- [ ] **Step 3: Write the handler**

Create `src/upwork_bot/bot/handlers/quiet_hours.py`:

```python
from datetime import datetime, time

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_QUIET_HOURS,
    BTN_QUIET_SET_WINDOW,
    BTN_QUIET_TOGGLE_OFF,
    BTN_QUIET_TOGGLE_ON,
    cancel_kb,
    quiet_hours_menu_kb,
    settings_menu_kb,
)
from upwork_bot.bot.states import QuietHoursStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import set_quiet_hours_enabled, set_quiet_window

router = Router(name="quiet_hours")


def _parse_hhmm(text: str | None) -> time | None:
    try:
        parsed = datetime.strptime((text or "").strip(), "%H:%M")
    except ValueError:
        return None
    return parsed.time()


def _status(user: User) -> str:
    state = "on" if user.quiet_hours_enabled else "off"
    tz = user.timezone or "not set"
    if user.quiet_start and user.quiet_end:
        window = f"{user.quiet_start.strftime('%H:%M')}–{user.quiet_end.strftime('%H:%M')}"
    else:
        window = "not set"
    return (
        f"<b>Quiet hours</b>: {state}\nWindow (local): {window}\nTimezone: {tz}\n\n"
        "During quiet hours parsing is suspended and jobs that arrive are skipped."
    )


@router.message(lambda m: m.text == BTN_QUIET_HOURS)
async def open_quiet_hours(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer(
        _status(user), reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled)
    )


@router.message(lambda m: m.text in (BTN_QUIET_TOGGLE_ON, BTN_QUIET_TOGGLE_OFF))
async def toggle_quiet_hours(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    enabling = message.text == BTN_QUIET_TOGGLE_ON
    if enabling and not user.timezone:
        await message.answer(
            "Set your 🕒 Timezone first — quiet hours need it.",
            reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled),
        )
        return
    async with AsyncSessionLocal() as session:
        await set_quiet_hours_enabled(session, user.telegram_id, enabling)
    user.quiet_hours_enabled = enabling
    await message.answer(
        _status(user), reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled)
    )


@router.message(lambda m: m.text == BTN_QUIET_SET_WINDOW)
async def start_set_window(message: Message, state: FSMContext, user: User) -> None:
    await state.set_state(QuietHoursStates.waiting_for_start)
    await message.answer(
        "Send the quiet-hours <b>start</b> time as HH:MM (24h), e.g. 23:00.",
        reply_markup=cancel_kb(),
    )


@router.message(QuietHoursStates.waiting_for_start)
async def process_start(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled)
        )
        return
    if _parse_hhmm(message.text) is None:
        await message.answer("Send a time as HH:MM, e.g. 23:00.")
        return
    await state.update_data(quiet_start=message.text.strip())
    await state.set_state(QuietHoursStates.waiting_for_end)
    await message.answer("Now send the <b>end</b> time as HH:MM, e.g. 07:00.")


@router.message(QuietHoursStates.waiting_for_end)
async def process_end(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled)
        )
        return
    end = _parse_hhmm(message.text)
    if end is None:
        await message.answer("Send a time as HH:MM, e.g. 07:00.")
        return
    data = await state.get_data()
    start = _parse_hhmm(data.get("quiet_start"))
    if start is None or start == end:
        await state.clear()
        await message.answer(
            "Start and end can't be equal — start over with 🕐 Set window.",
            reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled),
        )
        return
    async with AsyncSessionLocal() as session:
        await set_quiet_window(session, user.telegram_id, start, end)
    user.quiet_start, user.quiet_end = start, end
    await state.clear()
    await message.answer(
        f"✅ Quiet hours window set to {start.strftime('%H:%M')}–{end.strftime('%H:%M')}.",
        reply_markup=quiet_hours_menu_kb(user.quiet_hours_enabled),
    )
```

- [ ] **Step 4: Register the router**

In `src/upwork_bot/bot/main.py`, add `quiet_hours` to the handlers import and include it before `menu.router` (next to `timezone.router`):

```python
    dispatcher.include_router(timezone.router)
    dispatcher.include_router(quiet_hours.router)
    dispatcher.include_router(setup.router)
```

(Add `quiet_hours` to the `from upwork_bot.bot.handlers import (...)` list.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_quiet_hours_handler.py -v`
Expected: PASS (all four tests).

- [ ] **Step 6: Commit**

```bash
git add src/upwork_bot/bot/handlers/quiet_hours.py src/upwork_bot/bot/main.py tests/test_quiet_hours_handler.py
git commit -m "feat: quiet-hours submenu (toggle + window FSM)"
```

---

### Task 9: Setup guide copy + full suite gate

**Files:**
- Modify: `src/upwork_bot/bot/handlers/setup.py` (`_HOWTO` text)
- Test: whole suite

**Interfaces:**
- Consumes: everything above. No new code interfaces.

- [ ] **Step 1: Update the setup guide copy**

In `src/upwork_bot/bot/handlers/setup.py`, extend `_HOWTO` with a line about the new controls — add before the closing `)` of `_HOWTO`:

```python
        "\n8. ⚙️ Settings → 🕒 Timezone, then 🌙 Quiet hours to pause parsing overnight. "
        "Use ▶️/⏸ on the main menu to start or pause parsing anytime."
```

(Append it as an additional string literal in the existing implicitly-concatenated tuple.)

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest`
Expected: PASS — all tests, including the pre-existing suite.

- [ ] **Step 3: Lint + format gate**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: no errors. If format check fails, run `uv run ruff format .` and re-run.

- [ ] **Step 4: Commit**

```bash
git add src/upwork_bot/bot/handlers/setup.py
git commit -m "docs: mention quiet hours + parsing toggle in setup guide"
```

---

## Notes for the implementer

- Postgres must be up for the DB-touching tests: `docker compose up -d db`, then `uv run alembic upgrade head` once (Task 1 Step 5).
- The DROP semantics are entirely emergent from advancing the mailbox cursor while suspended — there is no separate "mark seen" step to write. Do not add one.
- `main_menu_kb(parsing_active=True)` default keeps the six `proposals.py` call sites compiling unchanged; their fallback keyboard showing the default toggle is acceptable (cosmetic). Do not widen scope to thread `user` through proposals.

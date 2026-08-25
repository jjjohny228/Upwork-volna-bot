# Quiet Hours + Parsing Start/Pause — Design

Date: 2026-08-25

## Goal

Let each user control **when** the bot parses their Gmail job alerts, so a deployed
server does not push jobs (or spend LLM calls) while the user sleeps. Two
per-user controls:

1. **Quiet hours** — a daily local-time window during which parsing is suspended.
   Requires the user to pick a **timezone** (mandatory for the feature).
2. **Start/Pause parsing** — a manual on/off switch, independent of quiet hours.

Both are per-user, consistent with the multi-user architecture (users → mailboxes).

## Decisions (from brainstorming)

- **Timezone selection UX:** inline keyboard of ~12 common IANA zones, plus an
  "enter manually" path (free-text IANA name, validated). IANA names chosen over
  fixed UTC offsets so DST is handled automatically by `zoneinfo`.
- **During quiet hours / pause: DROP.** Emails that arrive while parsing is
  suspended are never processed and never delivered — they are marked read/skipped
  by the existing `since`-cutoff path (see Poller). No catch-up flood on wake.
- **Placement:** Start/Pause lives on the **main menu** (quick access); quiet
  hours + timezone live under **⚙️ Settings**.

## Data model

New columns on `User` (`src/upwork_bot/db/models.py`), added by migration `0010`:

| column                | type          | default        | notes                                              |
|-----------------------|---------------|----------------|----------------------------------------------------|
| `timezone`            | `Text`        | NULL           | IANA name, e.g. `Europe/Kyiv`. Required for quiet. |
| `parsing_active`      | `Boolean`     | `true`         | Manual start/pause switch.                         |
| `quiet_hours_enabled` | `Boolean`     | `false`        | Quiet-hours master toggle.                         |
| `quiet_start`         | `Time`        | NULL           | Local wall-clock start (no tz).                    |
| `quiet_end`           | `Time`        | NULL           | Local wall-clock end (no tz).                      |

- Defaults preserve current behavior: every existing user keeps parsing on, quiet
  off. No data backfill required.
- `quiet_start`/`quiet_end` are naive `datetime.time`; they are interpreted in the
  user's `timezone`.
- Migration `0010`: `add_column` each with server defaults on upgrade; drop them on
  downgrade. `Revises: 0009`.

## Gating logic

Pure, side-effect-free helper (unit-testable), e.g. in
`src/upwork_bot/gmail/schedule.py`:

```python
def is_parsing_allowed(user: User, now_utc: datetime) -> bool:
    if not user.parsing_active:
        return False
    if not (user.quiet_hours_enabled and user.timezone
            and user.quiet_start and user.quiet_end):
        return True
    local = now_utc.astimezone(ZoneInfo(user.timezone)).time()
    start, end = user.quiet_start, user.quiet_end
    if start <= end:                      # same-day window
        in_quiet = start <= local < end
    else:                                 # wraps past midnight
        in_quiet = local >= start or local < end
    return not in_quiet
```

- No timezone → quiet hours cannot be active (UI prevents enabling without one), so
  parsing stays allowed unless manually paused.
- `start == end` is treated as an empty window (same-day branch, `start <= t < start`
  is always false) → parsing allowed. The set-window flow should reject equal times.

## Poller changes (`src/upwork_bot/gmail/poller.py`)

`poll_once` currently loops active mailboxes and always fetches. Change:

1. Load owners once per cycle into a `{user_id: User}` map (few users; one query).
2. For each mailbox, resolve `owner = owners.get(mb.user_id)`.
3. If `owner is None` or `not is_parsing_allowed(owner, now_utc)`:
   - **Advance the mailbox cursor to `poll_start`** (`set_mailbox_cursor`) and
     `continue`. No IMAP connection, no LLM.
4. Otherwise fetch + process exactly as today.

Why advancing the cursor implements DROP: on the next *allowed* poll, `mb_since`
= the advanced cursor (≈ the moment the window ended). `fetch_new_job_emails`
searches `UNSEEN ... SINCE <date>` and then, per message, marks any email with
`msg_date < since` as `\Seen` and skips it. So emails that arrived during the quiet
window fall below `since` and are dropped, never parsed or delivered.

Edge note (acceptable): emails from a calendar day entirely before the resume day
(e.g. arrived 23:30, window ends 07:00 next day) are never matched by the
date-granular `SINCE` and simply remain unread in Gmail — still dropped from the
bot's perspective, only cosmetically unread in the inbox.

## Repo functions (`src/upwork_bot/db/repo.py`)

Follow the existing `set_*` pattern (look up by `telegram_id`, mutate, commit,
return bool):

- `set_timezone(session, telegram_id, tz: str) -> bool`
- `set_parsing_active(session, telegram_id, active: bool) -> bool`
- `set_quiet_hours_enabled(session, telegram_id, enabled: bool) -> bool`
- `set_quiet_window(session, telegram_id, start: time, end: time) -> bool`

## Bot UI

### Main menu — Start/Pause

- `main_menu_kb(parsing_active: bool)` gains a parameter and a toggle row:
  `⏸ Pause parsing` when active, `▶️ Start parsing` when paused (mirrors the
  delivery-mode dynamic-label pattern in `settings_menu_kb`).
- All callers pass `user.parsing_active`. Affected handlers gain a `user: User`
  param where missing: `menu.cmd_start`, `menu.go_back_to_main_menu`,
  `setup.show_setup` (already has `user`).
- New handlers in `menu.py` matching the two labels: flip `parsing_active` via
  `set_parsing_active`, update in-memory `user`, re-render main menu with a
  confirmation line.

### Settings menu

`settings_menu_kb` gains two buttons: `🌙 Quiet hours`, `🕒 Timezone`.

### Timezone (`src/upwork_bot/bot/handlers/timezone.py`)

- `🕒 Timezone` → message showing current tz + inline keyboard: ~12 common IANA
  zones (e.g. `Europe/Kyiv`, `Europe/London`, `Europe/Berlin`, `America/New_York`,
  `America/Los_Angeles`, `America/Chicago`, `Asia/Dubai`, `Asia/Kolkata`,
  `Asia/Singapore`, `Asia/Tokyo`, `Australia/Sydney`, `UTC`) + `✍️ Enter manually`.
- Zone callback → `set_timezone`, confirm.
- Manual → `TimezoneStates.waiting_for_manual`; validate with
  `ZoneInfo(name)` (reject on `ZoneInfoNotFoundError`); on success `set_timezone`.

### Quiet hours (`src/upwork_bot/bot/handlers/quiet_hours.py`)

- `quiet_hours_menu_kb()` submenu showing current state (enabled?, window, tz):
  - Toggle button `🔔 Enable quiet hours` / `🔕 Disable quiet hours`.
    Enabling with no timezone set → reject with a hint to set timezone first
    (do not enable).
  - `🕐 Set window` → FSM: prompt start (`HH:MM`), then end (`HH:MM`);
    validate each with `%H:%M`; reject `start == end`; persist via
    `set_quiet_window`.
  - `⬅️ Back`.

### States (`src/upwork_bot/bot/states.py`)

```python
class TimezoneStates(StatesGroup):
    waiting_for_manual = State()

class QuietHoursStates(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()
```

### Wiring

Register `timezone.router` and `quiet_hours.router` in `bot/main.py`
`create_dispatcher` (before the catch-all `menu.router`).

## Testing

- **`is_parsing_allowed`** (unit): paused; quiet-disabled; inside same-day window;
  outside; midnight-wrap inside/outside; timezone conversion (window in local time,
  `now` in UTC); missing tz → allowed; `start == end` → allowed.
- **Poller**: mailbox whose owner is paused/quiet → `fetch_new_job_emails` NOT
  called, `on_new_job` NOT called, cursor advanced to poll_start; allowed owner →
  fetch called and jobs delivered. Mock the client + repo.
- **Repo**: each new setter updates the row and returns True; False for unknown
  telegram_id.
- **Keyboards**: `main_menu_kb` shows Pause label when active / Start when paused;
  `settings_menu_kb` includes the two new buttons.
- **Handlers**: toggle parsing flips flag and re-renders; timezone valid/invalid;
  quiet window valid/invalid and equal-times rejected; enable-quiet-without-tz
  rejected.

## Files touched

- `src/upwork_bot/db/models.py` — new User columns.
- `migrations/versions/0010_*.py` — new migration.
- `src/upwork_bot/db/repo.py` — new setters.
- `src/upwork_bot/gmail/schedule.py` — new `is_parsing_allowed`.
- `src/upwork_bot/gmail/poller.py` — gating in `poll_once`.
- `src/upwork_bot/bot/keyboards.py` — main-menu toggle, settings buttons,
  quiet-hours submenu, timezone inline kb.
- `src/upwork_bot/bot/states.py` — new state groups.
- `src/upwork_bot/bot/handlers/menu.py` — start/pause handlers, `main_menu_kb`
  callers pass `parsing_active`.
- `src/upwork_bot/bot/handlers/timezone.py` — new.
- `src/upwork_bot/bot/handlers/quiet_hours.py` — new.
- `src/upwork_bot/bot/main.py` — register routers.
- Tests under `tests/`.

## Out of scope (YAGNI)

- Multiple quiet windows per day.
- Per-mailbox (vs per-user) scheduling.
- Global/admin default schedules.
- Timezone auto-detection from location.

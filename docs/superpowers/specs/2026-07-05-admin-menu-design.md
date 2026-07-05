# Admin Menu (Reply-Keyboard + FSM) Design

## Goal

Replace every owner-facing command that currently requires typing arguments inline (`/addfeed <url> <label>`, `/removefeed <id>`, `/setresume <text>`, `/addproject <title> | <description> | <link>`, `/addexample <text>`, `/listfeeds`) with a persistent reply-keyboard menu driven by aiogram FSM states — no more argument parsing from raw message text.

## Entry point

- `/start` (new command, doesn't exist yet) sends a welcome message and shows the **main menu** as a `ReplyKeyboardMarkup`, `resize_keyboard=True`.
- Main menu buttons: `📋 Feeds`, `📄 Resume`, `💼 Portfolio`, `✍️ Proposal examples`.
- Tapping a main-menu button replaces the keyboard with that section's **submenu** (also a `ReplyKeyboardMarkup`).

## Submenu shape (identical across all 4 sections)

- `📃 List` — lists existing rows for that section, one Telegram message per row, each with an inline keyboard `✖️` button that deletes that row on tap (`delfeed:<id>`, `delproject:<id>`, `delexample:<id>`). Resume has no list of rows (it's a single active row) — see Resume section below for its variant.
- `➕ Add` — starts an FSM sequence prompting one field at a time (exact fields per section below). Every prompt during an FSM sequence also shows a `❌ Cancel` reply-button; tapping it clears FSM state and returns to that section's submenu without saving anything.
- `⬅️ Back` — clears any in-progress FSM state (if the user was mid-`Add` and taps Back instead of Cancel, treat it identically to Cancel) and returns to the **main** menu.

### Feeds

- `📃 List feeds` — same content as today's `/listfeeds` (id, active/paused, label, url) but one message per feed with an inline `✖️` delete button.
- `➕ Add feed` — FSM: prompt "Send the RSS URL" (state `FeedStates.waiting_for_url`) → prompt "Send a label" (state `FeedStates.waiting_for_label`, URL stored in FSM data) → save via existing `add_feed`, confirm, return to Feeds submenu.

### Resume

- `👁 View resume` — shows the current resume content (or "No resume set yet" if `get_active_resume` returns `None`). No per-row delete (resume is a single active value, not a list).
- `✏️ Set resume` — FSM: prompt "Send resume text, or upload a .pdf/.docx" (state `ResumeStates.waiting_for_content`). The handler for this state accepts either a text `Message` or a `Message` with `.document` set (reusing the existing `_extract_text` pdf/docx logic), calls `upsert_resume`, confirms, returns to Resume submenu.

### Portfolio

- `📃 List projects` — one message per `PortfolioProject` (title, description, link if set) with an inline `✖️` delete button.
- `➕ Add project` — FSM: prompt "Send the project title" (`PortfolioStates.waiting_for_title`) → prompt "Send the description" (`waiting_for_description`) → prompt "Send a link, or tap Skip" with an inline `⏭️ Skip` button alongside the reply-keyboard Cancel (`waiting_for_link`) → embed `f"{title}\n{description}"`, save via `add_portfolio_project`, confirm, return to Portfolio submenu.

### Proposal examples

- `📃 List examples` — one message per `ProposalExample` (id + first ~80 chars of `source_text` as a preview) with an inline `✖️` delete button.
- `➕ Add example` — FSM: prompt "Send the text of a past proposal" (`ExampleStates.waiting_for_text`) → embed, save via `add_proposal_example`, confirm, return to Examples submenu.

## Removed

The following `Command` handlers are deleted entirely (superseded by the menu): `/addfeed`, `/removefeed`, `/listfeeds`, `/setresume`, `/addproject`, `/addexample`. The existing document-upload-without-command handler in `resume.py` (`@router.message(lambda message: message.document is not None)`) is removed as a standalone handler and folded into the `ResumeStates.waiting_for_content` FSM state instead — so uploading a random document outside that state no longer silently triggers a resume update (a pre-existing minor bug this redesign incidentally fixes: today any `.pdf`/`.docx` upload at any time overwrites the resume, regardless of context).

`/start` is added. No other commands remain.

## New repository functions

`portfolio_projects` and `proposal_examples` currently only support insert + similarity search — no list/remove, unlike `feeds`. Add, mirroring the existing `list_feeds`/`remove_feed` pattern in `db/repo.py`:

- `list_portfolio_projects(session) -> list[PortfolioProject]`
- `remove_portfolio_project(session, project_id: int) -> bool`
- `list_proposal_examples(session) -> list[ProposalExample]`
- `remove_proposal_example(session, example_id: int) -> bool`

## New/changed files

- **New** `src/upwork_bot/bot/keyboards.py` — shared reply/inline keyboard builders and button-label string constants (so label text isn't duplicated/hand-typed across handler files — a typo in a button label would silently break its matching handler).
- **New** `src/upwork_bot/bot/states.py` — `FeedStates`, `ResumeStates`, `PortfolioStates`, `ExampleStates` (`aiogram.fsm.state.StatesGroup`). The existing `ProposalFeedbackStates` in `bot/handlers/proposals.py` is untouched and stays where it is — it belongs to the proposal-regeneration flow, not the admin menu.
- **New** `src/upwork_bot/bot/handlers/menu.py` — `/start` handler (sends main menu) and the four main-menu button handlers (each replaces the keyboard with that section's submenu).
- **Rewritten** `src/upwork_bot/bot/handlers/feeds.py`, `resume.py`, `portfolio.py`, `proposal_examples.py` — `Command` handlers replaced by: one handler matching the section's `📃 List` button text, one matching `➕ Add` (kicks off the FSM sequence), one or more FSM-state message handlers for the sequence's steps, one handler matching `⬅️ Back`/`❌ Cancel` text within that section's states, and one `CallbackQuery` handler per section for the inline `✖️` delete button (and, for Portfolio, the inline `⏭️ Skip` button on the link step).
- `src/upwork_bot/bot/main.py` — register the new `menu.router` (must be included so `/start` and main-menu button presses are handled; order matters only in that FSM-state-scoped handlers should be registered so they take precedence over any looser text-matching handler, matching the existing pattern already established by `proposals.router`'s state-scoped handler).
- `src/upwork_bot/db/repo.py` — add the four new functions listed above.

## Interaction with the existing proposal-regeneration FSM

`ProposalFeedbackStates.waiting_for_feedback` (in `proposals.py`) is a separate `StatesGroup` from the four new admin-menu `StatesGroup`s. aiogram FSM storage keys state by `(chat_id, user_id)`, and since this is a single-user bot there's only ever one active state at a time regardless of which `StatesGroup` it belongs to — so a user can't simultaneously be "waiting for feed label" and "waiting for proposal feedback". This is existing, correct aiogram behavior; no new code needs to handle the interaction, it's called out here only so the implementer doesn't try to build unnecessary cross-state guards.

## Testing

- `tests/test_keyboards.py` — unit tests that each keyboard builder returns the expected button layout/labels (no live bot/db needed).
- Per-section tests (e.g. `tests/test_feeds_handlers.py`) covering the FSM sequence end-to-end against the live db (mirroring the existing `tests/test_repo.py` / `tests/test_poller.py` pattern: real `AsyncSessionLocal`, real insert/list/delete, asserting the FSM's `state.get_data()` carries the right fields between steps and the final save lands the right row). At minimum: add-feed happy path (url → label → row exists), delete-feed via inline callback, add-project with a skipped link, add-project with a provided link, delete-project, add-example, delete-example, set-resume via text.
- `tests/test_repo.py` — extend with the four new list/remove functions (live db), following the existing dedup-test style in that file.

## Out of scope (explicitly, to keep this focused)

- No pagination for `📃 List` — if the list grows long, `docs/superpowers/plans` will need a page-token/keyboard-based pager, but the plan and this codebase currently have "a handful of rows" (per this project's own README/CLAUDE.md invariant on not over-engineering for MVP scale), so a flat list is enough for now.
- No edit-in-place for existing feeds/projects/examples (only add + delete) — matches the pre-existing scope, nothing in the original 11-task plan had an edit flow either.
- No confirmation dialog before delete (`✖️` deletes immediately) — matches the low-stakes, single-user, easily-re-addable nature of this data; adding a confirm-step would be extra friction with no real safety benefit here.

# Admin Menu (Reply-Keyboard + FSM) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every argument-based owner command (`/addfeed`, `/removefeed`, `/listfeeds`, `/setresume`, `/addproject`, `/addexample`) with a persistent reply-keyboard admin menu driven by aiogram FSM states.

**Architecture:** A new `/start` command shows a main reply-keyboard menu (Feeds / Resume / Portfolio / Proposal examples). Each section has its own submenu (List / Add / Back) built from shared keyboard helpers. "Add" flows collect fields one message at a time via per-domain `StatesGroup`s; "List" flows render one message per row with an inline `✖️` delete button. Existing command handlers in `feeds.py`, `resume.py`, `portfolio.py`, `proposal_examples.py` are replaced in place; `db/repo.py` gains list/remove functions for portfolio projects and proposal examples (feeds already has them).

**Tech Stack:** aiogram 3.x (`ReplyKeyboardMarkup`, `InlineKeyboardMarkup`, FSM `StatesGroup`/`FSMContext`), SQLAlchemy 2.0 async, pytest + pytest-asyncio.

## Global Constraints

- Package/env manager: `uv` only.
- Lint/format: `uv run ruff check .` and `uv run ruff format --check .` must be clean before each commit.
- Every handler stays owner-only — no change needed to `OwnerOnlyMiddleware`, it already gates all `message`/`callback_query` events at the dispatcher level.
- All DB access is async (`AsyncSession`, `AsyncSessionLocal`).
- Every module lives under `src/upwork_bot/`.
- No pagination, no edit-in-place, no delete-confirmation dialog (see spec's "Out of scope").
- Button label text is the only thing that identifies a menu action (no FSM used for navigation itself, only for data-entry sequences) — so every button label used in a `lambda m: m.text == ...` filter must come from the shared constants in `bot/keyboards.py`, never a hand-typed string, to avoid silent mismatches.

---

## File Structure

```
src/upwork_bot/
  bot/
    keyboards.py        (new)  — reply/inline keyboard builders + button-label constants
    states.py           (new)  — FeedStates, ResumeStates, PortfolioStates, ExampleStates
    handlers/
      menu.py           (new)  — /start, main-menu navigation, generic Back-to-main
      feeds.py          (rewrite) — List/Add/Delete via menu + FSM
      resume.py         (rewrite) — View/Set via menu + FSM
      portfolio.py      (rewrite) — List/Add/Delete via menu + FSM (Skip-link)
      proposal_examples.py (rewrite) — List/Add/Delete via menu + FSM
    main.py             (modify) — register menu.router last
  db/
    repo.py             (modify) — add list/remove for portfolio + examples
tests/
  test_keyboards.py     (new)
  test_repo.py          (modify) — add list/remove coverage
  test_feeds_handlers.py (new)
  test_resume_handlers.py (new)
  test_portfolio_handlers.py (new)
  test_examples_handlers.py (new)
```

---

## Task 1: Repo functions — list/remove for portfolio projects and proposal examples

**Files:**
- Modify: `src/upwork_bot/db/repo.py`
- Test: `tests/test_repo.py`

**Interfaces:**
- Produces: `list_portfolio_projects(session: AsyncSession) -> list[PortfolioProject]`, `remove_portfolio_project(session: AsyncSession, project_id: int) -> bool`, `list_proposal_examples(session: AsyncSession) -> list[ProposalExample]`, `remove_proposal_example(session: AsyncSession, example_id: int) -> bool`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_repo.py`:

```python
from upwork_bot.db.models import PortfolioProject, ProposalExample
from upwork_bot.db.repo import (
    list_portfolio_projects,
    list_proposal_examples,
    remove_portfolio_project,
    remove_proposal_example,
)


@pytest.mark.asyncio
async def test_list_and_remove_portfolio_project():
    async with AsyncSessionLocal() as session:
        project = PortfolioProject(
            title="repo-test-project",
            description="d",
            link=None,
            embedding=[0.0] * 1536,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        projects = await list_portfolio_projects(session)
        assert any(p.id == project.id for p in projects)

        removed = await remove_portfolio_project(session, project.id)
        assert removed is True

        removed_again = await remove_portfolio_project(session, project.id)
        assert removed_again is False

        projects_after = await list_portfolio_projects(session)
        assert all(p.id != project.id for p in projects_after)


@pytest.mark.asyncio
async def test_list_and_remove_proposal_example():
    async with AsyncSessionLocal() as session:
        example = ProposalExample(source_text="repo-test-example", embedding=[0.0] * 1536)
        session.add(example)
        await session.commit()
        await session.refresh(example)

        examples = await list_proposal_examples(session)
        assert any(e.id == example.id for e in examples)

        removed = await remove_proposal_example(session, example.id)
        assert removed is True

        removed_again = await remove_proposal_example(session, example.id)
        assert removed_again is False

        examples_after = await list_proposal_examples(session)
        assert all(e.id != example.id for e in examples_after)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repo.py -v`
Expected: FAIL — `ImportError: cannot import name 'list_portfolio_projects'`

- [ ] **Step 3: Implement in db/repo.py**

Append to `src/upwork_bot/db/repo.py` (after `add_proposal_example`):

```python
async def list_portfolio_projects(session: AsyncSession) -> list[PortfolioProject]:
    result = await session.execute(select(PortfolioProject))
    return list(result.scalars())


async def remove_portfolio_project(session: AsyncSession, project_id: int) -> bool:
    project = await session.get(PortfolioProject, project_id)
    if project is None:
        return False
    await session.delete(project)
    await session.commit()
    return True


async def list_proposal_examples(session: AsyncSession) -> list[ProposalExample]:
    result = await session.execute(select(ProposalExample))
    return list(result.scalars())


async def remove_proposal_example(session: AsyncSession, example_id: int) -> bool:
    example = await session.get(ProposalExample, example_id)
    if example is None:
        return False
    await session.delete(example)
    await session.commit()
    return True
```

(`PortfolioProject`/`ProposalExample` are already imported at the top of `repo.py` — no import changes needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repo.py -v`
Expected: PASS (all tests in the file, including the two new ones)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/db/repo.py tests/test_repo.py
git commit -m "feat: add list/remove repo functions for portfolio projects and proposal examples"
```

---

## Task 2: Shared keyboards + FSM state definitions

**Files:**
- Create: `src/upwork_bot/bot/keyboards.py`
- Create: `src/upwork_bot/bot/states.py`
- Test: `tests/test_keyboards.py`

**Interfaces:**
- Produces (keyboards.py): constants `BTN_FEEDS`, `BTN_RESUME`, `BTN_PORTFOLIO`, `BTN_EXAMPLES`, `BTN_LIST_FEEDS`, `BTN_ADD_FEED`, `BTN_VIEW_RESUME`, `BTN_SET_RESUME`, `BTN_LIST_PROJECTS`, `BTN_ADD_PROJECT`, `BTN_LIST_EXAMPLES`, `BTN_ADD_EXAMPLE`, `BTN_BACK`, `BTN_CANCEL`, `BTN_SKIP_LINK`; functions `main_menu_kb()`, `feeds_menu_kb()`, `resume_menu_kb()`, `portfolio_menu_kb()`, `examples_menu_kb()`, `cancel_kb()` (all `-> ReplyKeyboardMarkup`), `delete_button_kb(prefix: str, item_id: int) -> InlineKeyboardMarkup`, `skip_link_kb() -> InlineKeyboardMarkup`.
- Produces (states.py): `FeedStates` (`waiting_for_url`, `waiting_for_label`), `ResumeStates` (`waiting_for_content`), `PortfolioStates` (`waiting_for_title`, `waiting_for_description`, `waiting_for_link`), `ExampleStates` (`waiting_for_text`) — all `aiogram.fsm.state.StatesGroup`.

- [ ] **Step 1: Write failing test**

Create `tests/test_keyboards.py`:

```python
from upwork_bot.bot.keyboards import (
    BTN_ADD_FEED,
    BTN_BACK,
    BTN_CANCEL,
    BTN_EXAMPLES,
    BTN_FEEDS,
    BTN_LIST_FEEDS,
    BTN_PORTFOLIO,
    BTN_RESUME,
    BTN_SKIP_LINK,
    cancel_kb,
    delete_button_kb,
    feeds_menu_kb,
    main_menu_kb,
    skip_link_kb,
)


def _flatten(keyboard) -> list[str]:
    return [button.text for row in keyboard.keyboard for button in row]


def test_main_menu_has_all_four_sections():
    labels = _flatten(main_menu_kb())
    assert set(labels) == {BTN_FEEDS, BTN_RESUME, BTN_PORTFOLIO, BTN_EXAMPLES}


def test_feeds_menu_has_list_add_back():
    labels = _flatten(feeds_menu_kb())
    assert set(labels) == {BTN_LIST_FEEDS, BTN_ADD_FEED, BTN_BACK}


def test_cancel_kb_has_only_cancel():
    labels = _flatten(cancel_kb())
    assert labels == [BTN_CANCEL]


def test_delete_button_kb_encodes_prefix_and_id():
    kb = delete_button_kb("delfeed", 7)
    button = kb.inline_keyboard[0][0]
    assert button.callback_data == "delfeed:7"


def test_skip_link_kb_callback_data():
    kb = skip_link_kb()
    button = kb.inline_keyboard[0][0]
    assert button.text == BTN_SKIP_LINK
    assert button.callback_data == "skip_link"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_keyboards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'upwork_bot.bot.keyboards'`

- [ ] **Step 3: Implement bot/keyboards.py**

```python
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_FEEDS = "📋 Feeds"
BTN_RESUME = "📄 Resume"
BTN_PORTFOLIO = "💼 Portfolio"
BTN_EXAMPLES = "✍️ Proposal examples"

BTN_LIST_FEEDS = "📃 List feeds"
BTN_ADD_FEED = "➕ Add feed"

BTN_VIEW_RESUME = "👁 View resume"
BTN_SET_RESUME = "✏️ Set resume"

BTN_LIST_PROJECTS = "📃 List projects"
BTN_ADD_PROJECT = "➕ Add project"

BTN_LIST_EXAMPLES = "📃 List examples"
BTN_ADD_EXAMPLE = "➕ Add example"

BTN_BACK = "⬅️ Back"
BTN_CANCEL = "❌ Cancel"
BTN_SKIP_LINK = "⏭️ Skip"


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FEEDS), KeyboardButton(text=BTN_RESUME)],
            [KeyboardButton(text=BTN_PORTFOLIO), KeyboardButton(text=BTN_EXAMPLES)],
        ],
        resize_keyboard=True,
    )


def feeds_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LIST_FEEDS), KeyboardButton(text=BTN_ADD_FEED)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def resume_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_VIEW_RESUME), KeyboardButton(text=BTN_SET_RESUME)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def portfolio_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LIST_PROJECTS), KeyboardButton(text=BTN_ADD_PROJECT)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def examples_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LIST_EXAMPLES), KeyboardButton(text=BTN_ADD_EXAMPLE)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def delete_button_kb(prefix: str, item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️", callback_data=f"{prefix}:{item_id}")]]
    )


def skip_link_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BTN_SKIP_LINK, callback_data="skip_link")]]
    )
```

- [ ] **Step 4: Implement bot/states.py**

```python
from aiogram.fsm.state import State, StatesGroup


class FeedStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_label = State()


class ResumeStates(StatesGroup):
    waiting_for_content = State()


class PortfolioStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_link = State()


class ExampleStates(StatesGroup):
    waiting_for_text = State()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_keyboards.py -v`
Expected: PASS (5/5)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot/keyboards.py src/upwork_bot/bot/states.py tests/test_keyboards.py
git commit -m "feat: add shared admin-menu keyboards and FSM state definitions"
```

---

## Task 3: Main menu (`/start` + navigation)

**Files:**
- Create: `src/upwork_bot/bot/handlers/menu.py`
- Modify: `src/upwork_bot/bot/main.py`

**Interfaces:**
- Consumes: `bot.keyboards.{BTN_FEEDS, BTN_RESUME, BTN_PORTFOLIO, BTN_EXAMPLES, BTN_BACK, main_menu_kb, feeds_menu_kb, resume_menu_kb, portfolio_menu_kb, examples_menu_kb}` (Task 2).
- Produces: `bot.handlers.menu.router` (aiogram `Router`, name `"menu"`) with `/start`, four main-menu button handlers, and one generic `BTN_BACK` handler that returns to the main menu.

- [ ] **Step 1: Write menu.py**

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_EXAMPLES,
    BTN_FEEDS,
    BTN_PORTFOLIO,
    BTN_RESUME,
    examples_menu_kb,
    feeds_menu_kb,
    main_menu_kb,
    portfolio_menu_kb,
    resume_menu_kb,
)

router = Router(name="menu")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Welcome to the Upwork Job-Hunter admin menu. Choose a section:",
        reply_markup=main_menu_kb(),
    )


@router.message(lambda m: m.text == BTN_FEEDS)
async def open_feeds_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Feeds:", reply_markup=feeds_menu_kb())


@router.message(lambda m: m.text == BTN_RESUME)
async def open_resume_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Resume:", reply_markup=resume_menu_kb())


@router.message(lambda m: m.text == BTN_PORTFOLIO)
async def open_portfolio_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Portfolio:", reply_markup=portfolio_menu_kb())


@router.message(lambda m: m.text == BTN_EXAMPLES)
async def open_examples_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Proposal examples:", reply_markup=examples_menu_kb())


@router.message(lambda m: m.text == BTN_BACK)
async def go_back_to_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb())
```

- [ ] **Step 2: Register menu.router in bot/main.py**

Modify `src/upwork_bot/bot/main.py` — add `menu` to the import from `upwork_bot.bot.handlers`, and register it **last** (domain routers' FSM-state-scoped handlers must get first look at a message, e.g. so pressing "⬅️ Back" while `FeedStates.waiting_for_url` is active is handled by `feeds.py`'s own state handler, not by this generic one — see Task 4's `process_feed_url`, which checks for `BTN_BACK`/`BTN_CANCEL` itself):

```python
from upwork_bot.bot.handlers import (
    feeds,
    jobs,
    menu,
    portfolio,
    proposal_examples,
    proposals,
    resume,
)
```

and in `create_dispatcher()`, after the existing `dispatcher.include_router(proposals.router)` line, add:

```python
    dispatcher.include_router(menu.router)
```

- [ ] **Step 3: Manual smoke check (bounded, real bot)**

The `.env` file already has real credentials from earlier tasks. Run a bounded check (do not leave this running):

```bash
timeout 15 uv run python -c "
import asyncio
from upwork_bot.bot.main import create_bot, create_dispatcher

async def main():
    bot = create_bot()
    dp = create_dispatcher()
    await dp.start_polling(bot)

asyncio.run(main())
" ; echo "EXIT_CODE=$?"
```

Expected: no traceback; exit code 124 (killed by timeout after connecting cleanly) is success. While this is running, send `/start` from the owner's Telegram account and confirm the main menu keyboard with all 4 section buttons appears.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot/handlers/menu.py src/upwork_bot/bot/main.py
git commit -m "feat: add /start and main admin-menu navigation"
```

---

## Task 4: Feeds section — List / Add / Delete via menu

**Files:**
- Modify: `src/upwork_bot/bot/handlers/feeds.py` (full rewrite)
- Test: `tests/test_feeds_handlers.py`

**Interfaces:**
- Consumes: `bot.keyboards.{BTN_LIST_FEEDS, BTN_ADD_FEED, BTN_BACK, BTN_CANCEL, cancel_kb, feeds_menu_kb, delete_button_kb}` (Task 2), `bot.states.FeedStates` (Task 2), `db.repo.{add_feed, list_feeds, remove_feed}` (pre-existing).
- Produces: `bot.handlers.feeds.router` with handlers `cmd_list_feeds`, `start_add_feed`, `process_feed_url`, `process_feed_label`, `delete_feed_callback` (functions importable by name for the test in this task).

- [ ] **Step 1: Write failing test**

Create `tests/test_feeds_handlers.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from sqlalchemy import select

from upwork_bot.bot.handlers.feeds import process_feed_label, process_feed_url, start_add_feed
from upwork_bot.bot.states import FeedStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import Feed


def _make_state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=42, user_id=42))


def _make_message(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_add_feed_happy_path():
    state = _make_state()

    with patch.object(Message, "answer", new_callable=AsyncMock):
        await start_add_feed(_make_message("➕ Add feed"), state)
        assert await state.get_state() == FeedStates.waiting_for_url.state

        await process_feed_url(_make_message("https://vollna.com/rss/menu-test"), state)
        assert await state.get_state() == FeedStates.waiting_for_label.state
        data = await state.get_data()
        assert data["url"] == "https://vollna.com/rss/menu-test"

        await process_feed_label(_make_message("menu-test-label"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Feed).where(Feed.url == "https://vollna.com/rss/menu-test")
        )
        feed = result.scalar_one()
        assert feed.label == "menu-test-label"

        await session.delete(feed)
        await session.commit()


@pytest.mark.asyncio
async def test_add_feed_cancel_does_not_save():
    state = _make_state()

    with patch.object(Message, "answer", new_callable=AsyncMock):
        await start_add_feed(_make_message("➕ Add feed"), state)
        await process_feed_url(_make_message("❌ Cancel"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Feed).where(Feed.label == "menu-test-label"))
        assert result.scalar_one_or_none() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_feeds_handlers.py -v`
Expected: FAIL — `ImportError` (handlers don't have this shape yet; `feeds.py` still has the old `Command`-based handlers)

- [ ] **Step 3: Rewrite feeds.py**

Replace the full contents of `src/upwork_bot/bot/handlers/feeds.py`:

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_ADD_FEED,
    BTN_BACK,
    BTN_CANCEL,
    BTN_LIST_FEEDS,
    cancel_kb,
    delete_button_kb,
    feeds_menu_kb,
)
from upwork_bot.bot.states import FeedStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_feed, list_feeds, remove_feed

router = Router(name="feeds")


@router.message(lambda m: m.text == BTN_LIST_FEEDS)
async def cmd_list_feeds(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        feeds = await list_feeds(session)

    if not feeds:
        await message.answer("No feeds configured.")
        return

    for feed in feeds:
        status = "active" if feed.is_active else "paused"
        await message.answer(
            f"#{feed.id} [{status}] {feed.label} — {feed.url}",
            reply_markup=delete_button_kb("delfeed", feed.id),
        )


@router.message(lambda m: m.text == BTN_ADD_FEED)
async def start_add_feed(message: Message, state: FSMContext) -> None:
    await state.set_state(FeedStates.waiting_for_url)
    await message.answer("Send the RSS URL.", reply_markup=cancel_kb())


@router.message(FeedStates.waiting_for_url)
async def process_feed_url(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=feeds_menu_kb())
        return

    await state.update_data(url=message.text)
    await state.set_state(FeedStates.waiting_for_label)
    await message.answer("Send a label for this feed.", reply_markup=cancel_kb())


@router.message(FeedStates.waiting_for_label)
async def process_feed_label(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=feeds_menu_kb())
        return

    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        feed = await add_feed(session, url=data["url"], label=message.text)
    await state.clear()
    await message.answer(f"Added feed #{feed.id}: {feed.label}", reply_markup=feeds_menu_kb())


@router.callback_query(lambda c: c.data.startswith("delfeed:"))
async def delete_feed_callback(callback: CallbackQuery) -> None:
    feed_id = int(callback.data.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_feed(session, feed_id)
    await callback.answer("Deleted." if removed else "Not found.")
    if removed:
        await callback.message.edit_text(callback.message.text + "\n\n(deleted)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_feeds_handlers.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Run full suite to check for regressions**

Run: `uv run pytest -v`
Expected: all tests pass (no other file imports the removed `Command`-based feed handlers)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot/handlers/feeds.py tests/test_feeds_handlers.py
git commit -m "feat: replace /addfeed /removefeed /listfeeds with menu-driven FSM flow"
```

---

## Task 5: Resume section — View / Set via menu

**Files:**
- Modify: `src/upwork_bot/bot/handlers/resume.py` (full rewrite)
- Test: `tests/test_resume_handlers.py`

**Interfaces:**
- Consumes: `bot.keyboards.{BTN_VIEW_RESUME, BTN_SET_RESUME, BTN_BACK, BTN_CANCEL, cancel_kb, resume_menu_kb}` (Task 2), `bot.states.ResumeStates` (Task 2), `db.repo.{get_active_resume, upsert_resume}` (pre-existing).
- Produces: `bot.handlers.resume.router` with handlers `view_resume`, `start_set_resume`, `process_resume_content`.

- [ ] **Step 1: Write failing test**

Create `tests/test_resume_handlers.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User

from upwork_bot.bot.handlers.resume import process_resume_content, start_set_resume
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import get_active_resume


def _make_state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=42, user_id=42))


def _make_message(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_set_resume_via_text():
    state = _make_state()

    with patch.object(Message, "answer", new_callable=AsyncMock):
        await start_set_resume(_make_message("✏️ Set resume"), state)
        await process_resume_content(_make_message("Menu-test resume content"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        content = await get_active_resume(session)
        assert content == "Menu-test resume content"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume_handlers.py -v`
Expected: FAIL — `ImportError` (old `resume.py` only has `cmd_setresume`/`handle_resume_document`)

- [ ] **Step 3: Rewrite resume.py**

Replace the full contents of `src/upwork_bot/bot/handlers/resume.py`:

```python
import io

import docx2txt
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pypdf import PdfReader

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_SET_RESUME,
    BTN_VIEW_RESUME,
    cancel_kb,
    resume_menu_kb,
)
from upwork_bot.bot.states import ResumeStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import get_active_resume, upsert_resume

router = Router(name="resume")


def _extract_text(filename: str, data: bytes) -> str:
    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if filename.endswith(".docx"):
        return docx2txt.process(io.BytesIO(data))
    return data.decode("utf-8", errors="ignore")


@router.message(lambda m: m.text == BTN_VIEW_RESUME)
async def view_resume(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        content = await get_active_resume(session)
    await message.answer(content or "No resume set yet.")


@router.message(lambda m: m.text == BTN_SET_RESUME)
async def start_set_resume(message: Message, state: FSMContext) -> None:
    await state.set_state(ResumeStates.waiting_for_content)
    await message.answer(
        "Send resume text, or upload a .pdf/.docx file.", reply_markup=cancel_kb()
    )


@router.message(ResumeStates.waiting_for_content)
async def process_resume_content(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=resume_menu_kb())
        return

    if message.document is not None:
        if not message.document.file_name or not message.document.file_name.endswith(
            (".pdf", ".docx")
        ):
            await message.answer("Only .pdf or .docx files are supported. Try again.")
            return
        file = await message.bot.get_file(message.document.file_id)
        buffer = await message.bot.download_file(file.file_path)
        content = _extract_text(message.document.file_name, buffer.read())
    elif message.text:
        content = message.text
    else:
        await message.answer("Send text or upload a .pdf/.docx file.")
        return

    async with AsyncSessionLocal() as session:
        await upsert_resume(session, content=content)
    await state.clear()
    await message.answer("Resume updated.", reply_markup=resume_menu_kb())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resume_handlers.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, commit**

```bash
uv run pytest -v
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot/handlers/resume.py tests/test_resume_handlers.py
git commit -m "feat: replace /setresume with menu-driven view/set FSM flow"
```

---

## Task 6: Portfolio section — List / Add (with Skip-link) / Delete via menu

**Files:**
- Modify: `src/upwork_bot/bot/handlers/portfolio.py` (full rewrite)
- Test: `tests/test_portfolio_handlers.py`

**Interfaces:**
- Consumes: `bot.keyboards.{BTN_LIST_PROJECTS, BTN_ADD_PROJECT, BTN_BACK, BTN_CANCEL, cancel_kb, portfolio_menu_kb, delete_button_kb, skip_link_kb}` (Task 2), `bot.states.PortfolioStates` (Task 2), `db.repo.{add_portfolio_project, list_portfolio_projects, remove_portfolio_project}` (Task 1 for list/remove), `llm.embeddings.embed_text` (pre-existing).
- Produces: `bot.handlers.portfolio.router` with handlers `cmd_list_projects`, `start_add_project`, `process_project_title`, `process_project_description`, `process_project_link`, `skip_project_link`, `delete_project_callback`.

- [ ] **Step 1: Write failing test**

Create `tests/test_portfolio_handlers.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from sqlalchemy import select

from upwork_bot.bot.handlers.portfolio import (
    process_project_description,
    process_project_link,
    start_add_project,
)
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import PortfolioProject


def _make_state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=42, user_id=42))


def _make_message(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_add_project_with_link():
    state = _make_state()

    fake_embedding = [0.0] * 1536
    with (
        patch.object(Message, "answer", new_callable=AsyncMock),
        patch("upwork_bot.bot.handlers.portfolio.embed_text", new=AsyncMock(return_value=fake_embedding)),
    ):
        await start_add_project(_make_message("➕ Add project"), state)
        await process_project_description(_make_message("menu-test-description"), state)
        # process_project_description expects title already stored; set it directly since
        # this test only exercises the description->link->save leg of the sequence.
        await state.update_data(title="menu-test-title")
        await process_project_description(_make_message("menu-test-description"), state)
        await process_project_link(_make_message("https://example.com/menu-test"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PortfolioProject).where(PortfolioProject.title == "menu-test-title")
        )
        project = result.scalar_one()
        assert project.description == "menu-test-description"
        assert project.link == "https://example.com/menu-test"

        await session.delete(project)
        await session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_portfolio_handlers.py -v`
Expected: FAIL — `ImportError` (old `portfolio.py` only has `cmd_addproject`)

- [ ] **Step 3: Rewrite portfolio.py**

Replace the full contents of `src/upwork_bot/bot/handlers/portfolio.py`:

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_ADD_PROJECT,
    BTN_BACK,
    BTN_CANCEL,
    BTN_LIST_PROJECTS,
    cancel_kb,
    delete_button_kb,
    portfolio_menu_kb,
    skip_link_kb,
)
from upwork_bot.bot.states import PortfolioStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import (
    add_portfolio_project,
    list_portfolio_projects,
    remove_portfolio_project,
)
from upwork_bot.llm.embeddings import embed_text

router = Router(name="portfolio")


@router.message(lambda m: m.text == BTN_LIST_PROJECTS)
async def cmd_list_projects(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        projects = await list_portfolio_projects(session)

    if not projects:
        await message.answer("No portfolio projects yet.")
        return

    for project in projects:
        link_line = f"\n{project.link}" if project.link else ""
        await message.answer(
            f"#{project.id} {project.title}\n{project.description}{link_line}",
            reply_markup=delete_button_kb("delproject", project.id),
        )


@router.message(lambda m: m.text == BTN_ADD_PROJECT)
async def start_add_project(message: Message, state: FSMContext) -> None:
    await state.set_state(PortfolioStates.waiting_for_title)
    await message.answer("Send the project title.", reply_markup=cancel_kb())


@router.message(PortfolioStates.waiting_for_title)
async def process_project_title(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=portfolio_menu_kb())
        return

    await state.update_data(title=message.text)
    await state.set_state(PortfolioStates.waiting_for_description)
    await message.answer("Send the project description.", reply_markup=cancel_kb())


@router.message(PortfolioStates.waiting_for_description)
async def process_project_description(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=portfolio_menu_kb())
        return

    await state.update_data(description=message.text)
    await state.set_state(PortfolioStates.waiting_for_link)
    await message.answer("Send a link, or tap Skip.", reply_markup=skip_link_kb())


async def _save_project(message: Message, state: FSMContext, link: str | None) -> None:
    data = await state.get_data()
    embedding = await embed_text(f"{data['title']}\n{data['description']}")
    async with AsyncSessionLocal() as session:
        project = await add_portfolio_project(
            session, data["title"], data["description"], link, embedding
        )
    await state.clear()
    await message.answer(
        f"Added project #{project.id}: {project.title}", reply_markup=portfolio_menu_kb()
    )


@router.message(PortfolioStates.waiting_for_link)
async def process_project_link(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=portfolio_menu_kb())
        return

    await _save_project(message, state, link=message.text)


@router.callback_query(lambda c: c.data == "skip_link", PortfolioStates.waiting_for_link)
async def skip_project_link(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _save_project(callback.message, state, link=None)


@router.callback_query(lambda c: c.data.startswith("delproject:"))
async def delete_project_callback(callback: CallbackQuery) -> None:
    project_id = int(callback.data.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_portfolio_project(session, project_id)
    await callback.answer("Deleted." if removed else "Not found.")
    if removed:
        await callback.message.edit_text(callback.message.text + "\n\n(deleted)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_portfolio_handlers.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, commit**

```bash
uv run pytest -v
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot/handlers/portfolio.py tests/test_portfolio_handlers.py
git commit -m "feat: replace /addproject with menu-driven list/add/delete FSM flow"
```

---

## Task 7: Proposal examples section — List / Add / Delete via menu

**Files:**
- Modify: `src/upwork_bot/bot/handlers/proposal_examples.py` (full rewrite)
- Test: `tests/test_examples_handlers.py`

**Interfaces:**
- Consumes: `bot.keyboards.{BTN_LIST_EXAMPLES, BTN_ADD_EXAMPLE, BTN_BACK, BTN_CANCEL, cancel_kb, examples_menu_kb, delete_button_kb}` (Task 2), `bot.states.ExampleStates` (Task 2), `db.repo.{add_proposal_example, list_proposal_examples, remove_proposal_example}` (Task 1 for list/remove), `llm.embeddings.embed_text` (pre-existing).
- Produces: `bot.handlers.proposal_examples.router` with handlers `cmd_list_examples`, `start_add_example`, `process_example_text`, `delete_example_callback`.

- [ ] **Step 1: Write failing test**

Create `tests/test_examples_handlers.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from sqlalchemy import select

from upwork_bot.bot.handlers.proposal_examples import process_example_text, start_add_example
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import ProposalExample


def _make_state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=42, user_id=42))


def _make_message(text: str) -> Message:
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="owner"),
        text=text,
    )


@pytest.mark.asyncio
async def test_add_example_happy_path():
    state = _make_state()
    fake_embedding = [0.0] * 1536

    with (
        patch.object(Message, "answer", new_callable=AsyncMock),
        patch(
            "upwork_bot.bot.handlers.proposal_examples.embed_text",
            new=AsyncMock(return_value=fake_embedding),
        ),
    ):
        await start_add_example(_make_message("➕ Add example"), state)
        await process_example_text(_make_message("menu-test example text"), state)
        assert await state.get_state() is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ProposalExample).where(ProposalExample.source_text == "menu-test example text")
        )
        example = result.scalar_one()

        await session.delete(example)
        await session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_examples_handlers.py -v`
Expected: FAIL — `ImportError` (old `proposal_examples.py` only has `cmd_addexample`)

- [ ] **Step 3: Rewrite proposal_examples.py**

Replace the full contents of `src/upwork_bot/bot/handlers/proposal_examples.py`:

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_ADD_EXAMPLE,
    BTN_BACK,
    BTN_CANCEL,
    BTN_LIST_EXAMPLES,
    cancel_kb,
    delete_button_kb,
    examples_menu_kb,
)
from upwork_bot.bot.states import ExampleStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import (
    add_proposal_example,
    list_proposal_examples,
    remove_proposal_example,
)
from upwork_bot.llm.embeddings import embed_text

router = Router(name="proposal_examples")


@router.message(lambda m: m.text == BTN_LIST_EXAMPLES)
async def cmd_list_examples(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        examples = await list_proposal_examples(session)

    if not examples:
        await message.answer("No proposal examples yet.")
        return

    for example in examples:
        preview = example.source_text[:80]
        await message.answer(
            f"#{example.id} {preview}",
            reply_markup=delete_button_kb("delexample", example.id),
        )


@router.message(lambda m: m.text == BTN_ADD_EXAMPLE)
async def start_add_example(message: Message, state: FSMContext) -> None:
    await state.set_state(ExampleStates.waiting_for_text)
    await message.answer("Send the text of a past proposal.", reply_markup=cancel_kb())


@router.message(ExampleStates.waiting_for_text)
async def process_example_text(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=examples_menu_kb())
        return

    embedding = await embed_text(message.text)
    async with AsyncSessionLocal() as session:
        example = await add_proposal_example(session, message.text, embedding)
    await state.clear()
    await message.answer(f"Added proposal example #{example.id}", reply_markup=examples_menu_kb())


@router.callback_query(lambda c: c.data.startswith("delexample:"))
async def delete_example_callback(callback: CallbackQuery) -> None:
    example_id = int(callback.data.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_proposal_example(session, example_id)
    await callback.answer("Deleted." if removed else "Not found.")
    if removed:
        await callback.message.edit_text(callback.message.text + "\n\n(deleted)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_examples_handlers.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite, lint, commit**

```bash
uv run pytest -v
uv run ruff check . && uv run ruff format --check .
git add src/upwork_bot/bot/handlers/proposal_examples.py tests/test_examples_handlers.py
git commit -m "feat: replace /addexample with menu-driven list/add/delete FSM flow"
```

---

## Task 8: Full manual Telegram verification + docs update

**Files:**
- Modify: `README.md` (command table)
- No new source files — this task verifies the whole feature live and updates user-facing docs.

**Interfaces:**
- Consumes: everything from Tasks 1-7.

- [ ] **Step 1: Update README's command table**

In `README.md`, replace the existing "Bot commands" table (which lists `/addfeed`, `/removefeed`, `/listfeeds`, `/setresume`, `/addproject`, `/addexample`) with:

```markdown
## Bot commands

Send `/start` to open the admin menu — every action below is reachable from there (Feeds / Resume / Portfolio / Proposal examples), no command arguments needed:

| Section | Actions |
|---|---|
| 📋 Feeds | List feeds (with ✖️ delete), Add feed (URL → label) |
| 📄 Resume | View resume, Set resume (paste text or upload `.pdf`/`.docx`) |
| 💼 Portfolio | List projects (with ✖️ delete), Add project (title → description → link or Skip) |
| ✍️ Proposal examples | List examples (with ✖️ delete), Add example (paste text) |
```

- [ ] **Step 2: Full bounded manual verification against the real bot**

Ensure `docker compose up -d db` is running and `.env` is populated. Run:

```bash
timeout 120 uv run python -m upwork_bot.app ; echo "EXIT_CODE=$?"
```

While it's running, from the owner's real Telegram account:
1. Send `/start` → main menu appears.
2. Tap `📋 Feeds` → `📃 List feeds` / `➕ Add feed` / `⬅️ Back` appear.
3. Tap `➕ Add feed` → send a URL → send a label → confirm "Added feed #N" and the Feeds submenu returns.
4. Tap `📃 List feeds` → confirm the new feed appears with a ✖️ button; tap it → confirm the row is marked deleted and a second tap on `📃 List feeds` no longer shows it.
5. Tap `⬅️ Back` → confirm main menu returns.
6. Repeat the Add→List→Delete cycle for `💼 Portfolio` (including tapping `⏭️ Skip` once instead of sending a link) and `✍️ Proposal examples`.
7. Tap `📄 Resume` → `👁 View resume` → confirm it shows the resume seeded in Task 7 of the original plan → `✏️ Set resume` → send new text → confirm `👁 View resume` reflects the update.
8. Confirm the pre-existing `Generate proposal` / `Regenerate with edits` job-card flow (from the original plan's Tasks 9-10) still works unaffected — this menu work doesn't touch `jobs.py`/`proposals.py`.

Expected: exit code 124 (bounded timeout success) after all of the above is confirmed working.

- [ ] **Step 3: Final full-suite check**

```bash
uv run pytest -v
uv run ruff check . && uv run ruff format --check .
```

Expected: all tests pass, lint clean.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for menu-driven admin commands"
```

---

## Self-Review Notes

- Spec coverage: entry point/`​/start` (Task 3), all 4 submenus' List/Add/Delete (Tasks 4, 6, 7) and Resume's View/Set variant (Task 5), repo list/remove additions (Task 1), shared keyboards/states (Task 2), removal of old commands (each rewrite task deletes the `Command` handlers it replaces), README update (Task 8) — every spec section maps to a task.
- Naming consistency checked: `PortfolioStates.waiting_for_link` (Task 2) matches the state used in `portfolio.py`'s `process_project_link`/`skip_project_link` (Task 6); `delete_button_kb(prefix, item_id)` (Task 2) is called consistently as `delete_button_kb("delfeed", feed.id)` / `"delproject"` / `"delexample"` across Tasks 4/6/7, matching each domain's callback-data prefix check (`c.data.startswith("delfeed:")` etc.).
- `BTN_BACK`/`BTN_CANCEL` handling is duplicated per FSM-state handler (checked inline in every `process_*` function) rather than centralized, because aiogram dispatches to the first matching handler by registration order — centralizing it in `menu.router` would require registering `menu.router` before the domain routers, which would then make the generic Back handler intercept messages meant for a domain's state handler. Task 3 registers `menu.router` last specifically so each domain's own state handler gets first look and can decide for itself whether the message is Back/Cancel or real input.

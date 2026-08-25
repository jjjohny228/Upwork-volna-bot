from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from upwork_bot.bot.keyboards import BTN_SETUP, main_menu_kb
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import (
    get_active_resume,
    list_portfolio_projects,
    list_proposal_examples,
    list_user_mailboxes,
)

router = Router(name="setup")

_HOWTO = (
    "How to set up:\n"
    "1. ⚙️ Settings → 📮 Mailboxes → ➕ Add mailbox. Use a Gmail App Password "
    "(Google account → 2-Step Verification on → enable IMAP → create an App Password). "
    "Jobs are polled from every mailbox you add.\n"
    "2. 📄 Resume → set your resume (text or .pdf/.docx).\n"
    "3. 💼 Portfolio → add your projects (used to match jobs and write proposals).\n"
    "4. ✍️ Proposal examples → paste a few past proposals as style reference.\n"
    "5. ⚙️ Settings → 🎯 Qualify prompt → ✨ Generate prompt (needs a resume + a project).\n"
    "6. ⚙️ Settings → 💲 Hourly rate and ✒️ Signature for proposal drafts.\n"
    "7. ⚙️ Settings → choose whether to receive all jobs or only qualified ones."
)


def _check(label: str, done: bool) -> str:
    return f"{'✅' if done else '❌'} {label}"


@router.message(lambda m: m.text == BTN_SETUP)
async def show_setup(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        mailboxes = await list_user_mailboxes(session, user.id)
        resume = await get_active_resume(session, user.id)
        projects = await list_portfolio_projects(session, user.id)
        examples = await list_proposal_examples(session, user.id)

    checklist = "\n".join(
        [
            _check("Mailbox connected", bool(mailboxes)),
            _check("Resume set", bool(resume)),
            _check("At least one portfolio project", bool(projects)),
            _check("At least one proposal example", bool(examples)),
            _check("Qualify prompt set", bool(user.analysis_prompt)),
            _check("Hourly rate set", bool(user.hourly_rate)),
        ]
    )
    await message.answer(
        f"<b>Your setup</b>\n{checklist}\n\n{_HOWTO}",
        reply_markup=main_menu_kb(user.parsing_active),
    )

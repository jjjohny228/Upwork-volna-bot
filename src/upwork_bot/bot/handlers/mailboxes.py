from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_ADD_MAILBOX,
    BTN_BACK,
    BTN_CANCEL,
    BTN_LIST_MAILBOXES,
    BTN_MAILBOXES,
    cancel_kb,
    delete_button_kb,
    mailboxes_menu_kb,
    skip_folder_kb,
)
from upwork_bot.bot.states import MailboxStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.models import User
from upwork_bot.db.repo import add_mailbox, list_user_mailboxes, remove_mailbox

router = Router(name="mailboxes")


@router.message(lambda m: m.text == BTN_MAILBOXES)
async def open_mailboxes_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Your Gmail mailboxes. Vollna job-alert emails are polled from each one.",
        reply_markup=mailboxes_menu_kb(),
    )


@router.message(lambda m: m.text == BTN_LIST_MAILBOXES)
async def cmd_list_mailboxes(message: Message, user: User) -> None:
    async with AsyncSessionLocal() as session:
        mailboxes = await list_user_mailboxes(session, user.id)

    if not mailboxes:
        await message.answer("No mailboxes yet. Tap ➕ Add mailbox.")
        return

    for mb in mailboxes:
        status = "active" if mb.is_active else "paused"
        await message.answer(
            f"#{mb.id} {mb.address}\nfolder: {mb.mailbox} · {status}",
            reply_markup=delete_button_kb("delmailbox", mb.id),
        )


@router.message(lambda m: m.text == BTN_ADD_MAILBOX)
async def start_add_mailbox(message: Message, state: FSMContext) -> None:
    await state.set_state(MailboxStates.waiting_for_address)
    await message.answer("Send the Gmail address.", reply_markup=cancel_kb())


@router.message(MailboxStates.waiting_for_address)
async def process_mailbox_address(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=mailboxes_menu_kb())
        return

    await state.update_data(address=(message.text or "").strip())
    await state.set_state(MailboxStates.waiting_for_password)
    await message.answer(
        "Send the Gmail App Password (needs 2-Step Verification + IMAP enabled).",
        reply_markup=cancel_kb(),
    )


@router.message(MailboxStates.waiting_for_password)
async def process_mailbox_password(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=mailboxes_menu_kb())
        return

    # Gmail shows App Passwords with spaces; IMAP login wants them stripped.
    await state.update_data(app_password=(message.text or "").replace(" ", ""))
    await state.set_state(MailboxStates.waiting_for_folder)
    await message.answer(
        "Send the IMAP folder to watch, or tap Use INBOX.", reply_markup=skip_folder_kb()
    )


async def _save_mailbox(message: Message, state: FSMContext, user_id: int, folder: str) -> None:
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        mb = await add_mailbox(
            session,
            user_id,
            address=data["address"],
            app_password=data["app_password"],
            mailbox=folder,
        )
    await state.clear()
    await message.answer(
        f"Added mailbox #{mb.id}: {mb.address} (folder {mb.mailbox}).",
        reply_markup=mailboxes_menu_kb(),
    )


@router.message(MailboxStates.waiting_for_folder)
async def process_mailbox_folder(message: Message, state: FSMContext, user: User) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=mailboxes_menu_kb())
        return

    folder = (message.text or "").strip() or "INBOX"
    await _save_mailbox(message, state, user.id, folder)


@router.callback_query(lambda c: c.data == "skip_folder", MailboxStates.waiting_for_folder)
async def skip_mailbox_folder(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await callback.answer()
    await _save_mailbox(callback.message, state, user.id, "INBOX")


@router.callback_query(lambda c: c.data.startswith("delmailbox:"))
async def delete_mailbox_callback(callback: CallbackQuery, user: User) -> None:
    mailbox_id = int(callback.data.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_mailbox(session, mailbox_id, user.id)
    await callback.answer("Deleted." if removed else "Not found.")
    if removed:
        await callback.message.edit_text(callback.message.text + "\n\n(deleted)")

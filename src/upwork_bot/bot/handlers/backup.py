import html
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_BACKUP_DB,
    BTN_CANCEL,
    BTN_CONFIRM_RESTORE,
    BTN_RESTORE_DB,
    cancel_kb,
    confirm_restore_kb,
    settings_menu_kb,
)
from upwork_bot.bot.states import RestoreDbStates
from upwork_bot.config import is_admin
from upwork_bot.db.backup import BackupError, backup_filename, dump_database, restore_database
from upwork_bot.db.models import User

router = Router(name="backup")


@router.message(lambda m: m.text == BTN_BACKUP_DB)
async def send_db_backup(message: Message, state: FSMContext, user: User) -> None:
    if not is_admin(user.telegram_id):
        return
    await state.clear()
    await message.answer("⏳ Dumping database…")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = Path(tmp_dir) / backup_filename()
        try:
            await dump_database(dump_path)
        except BackupError as exc:
            await message.answer(f"❌ Backup failed:\n<pre>{html.escape(str(exc))}</pre>")
            return
        await message.answer_document(FSInputFile(dump_path), caption="📦 Postgres backup")


@router.message(lambda m: m.text == BTN_RESTORE_DB)
async def start_restore(message: Message, state: FSMContext, user: User) -> None:
    if not is_admin(user.telegram_id):
        return
    await state.set_state(RestoreDbStates.waiting_for_dump)
    await message.answer(
        '⚠️ Send the .dump file (from "Backup DB") to restore.\n'
        "This will <b>REPLACE all current data</b> and cannot be undone.",
        reply_markup=cancel_kb(),
    )


async def _stage_dump(message: Message, state: FSMContext) -> None:
    """Download the attached dump into FSM storage and ask for confirmation."""
    file = await message.bot.get_file(message.document.file_id)
    buffer = await message.bot.download_file(file.file_path)
    dump_bytes = buffer.read()

    await state.update_data(dump_bytes=dump_bytes, filename=message.document.file_name or "dump")
    await state.set_state(RestoreDbStates.waiting_for_confirmation)
    size_kb = len(dump_bytes) / 1024
    await message.answer(
        f"Received {message.document.file_name} ({size_kb:.1f} KB).\n"
        "⚠️ This will <b>irreversibly overwrite</b> the entire database. Confirm?",
        reply_markup=confirm_restore_kb(),
    )


@router.message(
    StateFilter(None),
    F.document.file_name.lower().endswith(".dump"),
)
async def receive_dump_anytime(message: Message, state: FSMContext, user: User) -> None:
    """Admin can drop a .dump file into the chat without pressing Restore first."""
    if not is_admin(user.telegram_id):
        return
    await _stage_dump(message, state)


@router.message(RestoreDbStates.waiting_for_dump)
async def receive_restore_dump(message: Message, state: FSMContext, user: User) -> None:
    if not is_admin(user.telegram_id):
        await state.clear()
        return

    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=settings_menu_kb(user.notify_qualified_only, True)
        )
        return

    if message.document is None:
        await message.answer("Send the .dump file, or Cancel.")
        return

    await _stage_dump(message, state)


@router.message(RestoreDbStates.waiting_for_confirmation)
async def confirm_restore(message: Message, state: FSMContext, user: User) -> None:
    if not is_admin(user.telegram_id):
        await state.clear()
        return

    if message.text != BTN_CONFIRM_RESTORE:
        await state.clear()
        await message.answer(
            "Cancelled.", reply_markup=settings_menu_kb(user.notify_qualified_only, True)
        )
        return

    data = await state.get_data()
    dump_bytes: bytes = data["dump_bytes"]
    await state.clear()
    await message.answer("⏳ Restoring database…")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = Path(tmp_dir) / Path(data.get("filename", "dump")).name
        dump_path.write_bytes(dump_bytes)
        try:
            await restore_database(dump_path)
        except BackupError as exc:
            await message.answer(
                f"❌ Restore failed (rolled back):\n<pre>{html.escape(str(exc))}</pre>",
                reply_markup=settings_menu_kb(user.notify_qualified_only, True),
            )
            return

    await message.answer(
        "✅ Database restored.",
        reply_markup=settings_menu_kb(user.notify_qualified_only, True),
    )

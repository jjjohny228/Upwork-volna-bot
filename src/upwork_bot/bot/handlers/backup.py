import asyncio
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from aiogram import Router
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
from upwork_bot.config import get_settings, is_admin
from upwork_bot.db.models import User

router = Router(name="backup")


def _pg_conn_args(parsed: ParseResult) -> list[str]:
    return [
        f"--host={parsed.hostname}",
        f"--port={parsed.port or 5432}",
        f"--username={parsed.username}",
        f"--dbname={(parsed.path or '').lstrip('/')}",
    ]


def _pg_env(parsed: ParseResult) -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": parsed.password or ""}


@router.message(lambda m: m.text == BTN_BACKUP_DB)
async def send_db_backup(message: Message, state: FSMContext, user: User) -> None:
    if not is_admin(user.telegram_id):
        return
    await state.clear()

    parsed = urlparse(get_settings().database_url)
    await message.answer("⏳ Dumping database…")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = Path(tmp_dir) / f"upwork_backup_{datetime.now(UTC):%Y%m%d_%H%M%S}.dump"
        try:
            proc = await asyncio.create_subprocess_exec(
                "pg_dump",
                *_pg_conn_args(parsed),
                "--format=custom",
                f"--file={dump_path}",
                env=_pg_env(parsed),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            await message.answer("❌ pg_dump is not installed in this container.")
            return

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            await message.answer(f"❌ Backup failed:\n<pre>{stderr.decode()[:3500]}</pre>")
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

    parsed = urlparse(get_settings().database_url)
    await message.answer("⏳ Restoring database…")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = Path(tmp_dir) / data.get("filename", "dump")
        dump_path.write_bytes(dump_bytes)

        try:
            proc = await asyncio.create_subprocess_exec(
                "pg_restore",
                *_pg_conn_args(parsed),
                "--clean",
                "--if-exists",
                "--no-owner",
                "--single-transaction",
                str(dump_path),
                env=_pg_env(parsed),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            await message.answer(
                "❌ pg_restore is not installed in this container.",
                reply_markup=settings_menu_kb(user.notify_qualified_only, True),
            )
            return

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            await message.answer(
                f"❌ Restore failed (rolled back):\n<pre>{stderr.decode()[:3500]}</pre>",
                reply_markup=settings_menu_kb(user.notify_qualified_only, True),
            )
            return

    await message.answer(
        "✅ Database restored.",
        reply_markup=settings_menu_kb(user.notify_qualified_only, True),
    )

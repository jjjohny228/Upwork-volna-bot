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
    await message.answer("Send resume text, or upload a .pdf/.docx file.", reply_markup=cancel_kb())


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

import io

import docx2txt
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from pypdf import PdfReader

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import upsert_resume

router = Router(name="resume")


def _extract_text(filename: str, data: bytes) -> str:
    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if filename.endswith(".docx"):
        return docx2txt.process(io.BytesIO(data))
    return data.decode("utf-8", errors="ignore")


@router.message(Command("setresume"))
async def cmd_setresume(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Send text after /setresume, or upload a .pdf/.docx as the next message."
        )
        return

    async with AsyncSessionLocal() as session:
        await upsert_resume(session, content=parts[1])
    await message.answer("Resume updated.")


@router.message(lambda message: message.document is not None)
async def handle_resume_document(message: Message) -> None:
    document = message.document
    if not document.file_name or not document.file_name.endswith((".pdf", ".docx")):
        return

    file = await message.bot.get_file(document.file_id)
    buffer = await message.bot.download_file(file.file_path)
    text = _extract_text(document.file_name, buffer.read())

    async with AsyncSessionLocal() as session:
        await upsert_resume(session, content=text)
    await message.answer("Resume updated from uploaded document.")

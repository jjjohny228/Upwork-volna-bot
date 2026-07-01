from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_portfolio_project
from upwork_bot.llm.embeddings import embed_text

router = Router(name="portfolio")


@router.message(Command("addproject"))
async def cmd_addproject(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or "|" not in parts[1]:
        await message.answer("Usage: /addproject <title> | <description> | <link>")
        return

    fields = [f.strip() for f in parts[1].split("|")]
    if len(fields) < 2:
        await message.answer("Usage: /addproject <title> | <description> | <link>")
        return

    title, description = fields[0], fields[1]
    link = fields[2] if len(fields) > 2 else None

    embedding = await embed_text(f"{title}\n{description}")

    async with AsyncSessionLocal() as session:
        project = await add_portfolio_project(session, title, description, link, embedding)

    await message.answer(f"Added project #{project.id}: {project.title}")

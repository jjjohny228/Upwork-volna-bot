from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_proposal_example
from upwork_bot.llm.embeddings import embed_text

router = Router(name="proposal_examples")


@router.message(Command("addexample"))
async def cmd_addexample(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /addexample <text of a past proposal>")
        return

    source_text = parts[1]
    embedding = await embed_text(source_text)

    async with AsyncSessionLocal() as session:
        example = await add_proposal_example(session, source_text, embedding)

    await message.answer(f"Added proposal example #{example.id}")

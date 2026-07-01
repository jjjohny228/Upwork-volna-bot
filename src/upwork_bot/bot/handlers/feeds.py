from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import add_feed, list_feeds, remove_feed

router = Router(name="feeds")


@router.message(Command("addfeed"))
async def cmd_addfeed(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /addfeed <rss_url> <label>")
        return

    _, url, label = parts
    async with AsyncSessionLocal() as session:
        feed = await add_feed(session, url=url, label=label)
    await message.answer(f"Added feed #{feed.id}: {feed.label}")


@router.message(Command("removefeed"))
async def cmd_removefeed(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /removefeed <id>")
        return

    feed_id = int(parts[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_feed(session, feed_id)
    await message.answer(f"Removed feed #{feed_id}" if removed else "No such feed")


@router.message(Command("listfeeds"))
async def cmd_listfeeds(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        feeds = await list_feeds(session)

    if not feeds:
        await message.answer("No feeds configured.")
        return

    lines = [
        f"#{f.id} [{'active' if f.is_active else 'paused'}] {f.label} — {f.url}" for f in feeds
    ]
    await message.answer("\n".join(lines))

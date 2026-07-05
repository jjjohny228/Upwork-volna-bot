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

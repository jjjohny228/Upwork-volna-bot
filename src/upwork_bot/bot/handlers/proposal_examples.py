from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_ADD_EXAMPLE,
    BTN_BACK,
    BTN_CANCEL,
    BTN_LIST_EXAMPLES,
    cancel_kb,
    delete_button_kb,
    examples_menu_kb,
)
from upwork_bot.bot.states import ExampleStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import (
    add_proposal_example,
    list_proposal_examples,
    remove_proposal_example,
)
from upwork_bot.llm.embeddings import embed_text

router = Router(name="proposal_examples")


@router.message(lambda m: m.text == BTN_LIST_EXAMPLES)
async def cmd_list_examples(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        examples = await list_proposal_examples(session)

    if not examples:
        await message.answer("No proposal examples yet.")
        return

    for example in examples:
        preview = example.source_text[:80]
        await message.answer(
            f"#{example.id} {preview}",
            reply_markup=delete_button_kb("delexample", example.id),
        )


@router.message(lambda m: m.text == BTN_ADD_EXAMPLE)
async def start_add_example(message: Message, state: FSMContext) -> None:
    await state.set_state(ExampleStates.waiting_for_text)
    await message.answer("Send the text of a past proposal.", reply_markup=cancel_kb())


@router.message(ExampleStates.waiting_for_text)
async def process_example_text(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=examples_menu_kb())
        return

    embedding = await embed_text(message.text)
    async with AsyncSessionLocal() as session:
        example = await add_proposal_example(session, message.text, embedding)
    await state.clear()
    await message.answer(f"Added proposal example #{example.id}", reply_markup=examples_menu_kb())


@router.callback_query(lambda c: c.data.startswith("delexample:"))
async def delete_example_callback(callback: CallbackQuery) -> None:
    example_id = int(callback.data.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_proposal_example(session, example_id)
    await callback.answer("Deleted." if removed else "Not found.")
    if removed:
        await callback.message.edit_text(callback.message.text + "\n\n(deleted)")

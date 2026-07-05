from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from upwork_bot.bot.keyboards import (
    BTN_ADD_PROJECT,
    BTN_BACK,
    BTN_CANCEL,
    BTN_LIST_PROJECTS,
    cancel_kb,
    delete_button_kb,
    portfolio_menu_kb,
    skip_link_kb,
)
from upwork_bot.bot.states import PortfolioStates
from upwork_bot.db.base import AsyncSessionLocal
from upwork_bot.db.repo import (
    add_portfolio_project,
    list_portfolio_projects,
    remove_portfolio_project,
)
from upwork_bot.llm.embeddings import embed_text

router = Router(name="portfolio")


@router.message(lambda m: m.text == BTN_LIST_PROJECTS)
async def cmd_list_projects(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        projects = await list_portfolio_projects(session)

    if not projects:
        await message.answer("No portfolio projects yet.")
        return

    for project in projects:
        link_line = f"\n{project.link}" if project.link else ""
        await message.answer(
            f"#{project.id} {project.title}\n{project.description}{link_line}",
            reply_markup=delete_button_kb("delproject", project.id),
        )


@router.message(lambda m: m.text == BTN_ADD_PROJECT)
async def start_add_project(message: Message, state: FSMContext) -> None:
    await state.set_state(PortfolioStates.waiting_for_title)
    await message.answer("Send the project title.", reply_markup=cancel_kb())


@router.message(PortfolioStates.waiting_for_title)
async def process_project_title(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=portfolio_menu_kb())
        return

    await state.update_data(title=message.text)
    await state.set_state(PortfolioStates.waiting_for_description)
    await message.answer("Send the project description.", reply_markup=cancel_kb())


@router.message(PortfolioStates.waiting_for_description)
async def process_project_description(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=portfolio_menu_kb())
        return

    await state.update_data(description=message.text)
    await state.set_state(PortfolioStates.waiting_for_link)
    await message.answer("Send a link, or tap Skip.", reply_markup=skip_link_kb())


async def _save_project(message: Message, state: FSMContext, link: str | None) -> None:
    data = await state.get_data()
    embedding = await embed_text(f"{data['title']}\n{data['description']}")
    async with AsyncSessionLocal() as session:
        project = await add_portfolio_project(
            session, data["title"], data["description"], link, embedding
        )
    await state.clear()
    await message.answer(
        f"Added project #{project.id}: {project.title}", reply_markup=portfolio_menu_kb()
    )


@router.message(PortfolioStates.waiting_for_link)
async def process_project_link(message: Message, state: FSMContext) -> None:
    if message.text in (BTN_BACK, BTN_CANCEL):
        await state.clear()
        await message.answer("Cancelled.", reply_markup=portfolio_menu_kb())
        return

    await _save_project(message, state, link=message.text)


@router.callback_query(lambda c: c.data == "skip_link", PortfolioStates.waiting_for_link)
async def skip_project_link(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _save_project(callback.message, state, link=None)


@router.callback_query(lambda c: c.data.startswith("delproject:"))
async def delete_project_callback(callback: CallbackQuery) -> None:
    project_id = int(callback.data.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        removed = await remove_portfolio_project(session, project_id)
    await callback.answer("Deleted." if removed else "Not found.")
    if removed:
        await callback.message.edit_text(callback.message.text + "\n\n(deleted)")

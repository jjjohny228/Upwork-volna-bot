from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_EXAMPLES,
    BTN_FEEDS,
    BTN_PORTFOLIO,
    BTN_RESUME,
    examples_menu_kb,
    feeds_menu_kb,
    main_menu_kb,
    portfolio_menu_kb,
    resume_menu_kb,
)

router = Router(name="menu")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Welcome to the Upwork Job-Hunter admin menu. Choose a section:",
        reply_markup=main_menu_kb(),
    )


@router.message(lambda m: m.text == BTN_FEEDS)
async def open_feeds_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Feeds:", reply_markup=feeds_menu_kb())


@router.message(lambda m: m.text == BTN_RESUME)
async def open_resume_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Resume:", reply_markup=resume_menu_kb())


@router.message(lambda m: m.text == BTN_PORTFOLIO)
async def open_portfolio_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Portfolio:", reply_markup=portfolio_menu_kb())


@router.message(lambda m: m.text == BTN_EXAMPLES)
async def open_examples_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Proposal examples:", reply_markup=examples_menu_kb())


@router.message(lambda m: m.text == BTN_BACK)
async def go_back_to_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Main menu:", reply_markup=main_menu_kb())

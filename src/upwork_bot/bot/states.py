from aiogram.fsm.state import State, StatesGroup


class FeedStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_label = State()


class ResumeStates(StatesGroup):
    waiting_for_content = State()


class PortfolioStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_link = State()


class ExampleStates(StatesGroup):
    waiting_for_text = State()

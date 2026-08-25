from aiogram.fsm.state import State, StatesGroup


class ResumeStates(StatesGroup):
    waiting_for_content = State()


class PortfolioStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_link = State()


class ExampleStates(StatesGroup):
    waiting_for_text = State()


class CustomProposalStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_feedback = State()


class MailboxStates(StatesGroup):
    waiting_for_address = State()
    waiting_for_password = State()
    waiting_for_folder = State()


class RateStates(StatesGroup):
    waiting_for_rate = State()


class SignatureStates(StatesGroup):
    waiting_for_signature = State()


class QualifyPromptStates(StatesGroup):
    waiting_for_prompt = State()

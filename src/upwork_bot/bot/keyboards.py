from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_RESUME = "📄 Resume"
BTN_PORTFOLIO = "💼 Portfolio"
BTN_EXAMPLES = "✍️ Proposal examples"
BTN_WRITE_PROPOSAL = "🖊 Write proposal"
BTN_SETTINGS = "⚙️ Settings"

BTN_DELIVERY_ALL = "📬 Send all jobs"
BTN_DELIVERY_QUALIFIED = "✅ Send only qualified"

BTN_VIEW_RESUME = "👁 View resume"
BTN_SET_RESUME = "✏️ Set resume"

BTN_LIST_PROJECTS = "📃 List projects"
BTN_ADD_PROJECT = "➕ Add project"

BTN_LIST_EXAMPLES = "📃 List examples"
BTN_ADD_EXAMPLE = "➕ Add example"

BTN_BACK = "⬅️ Back"
BTN_CANCEL = "❌ Cancel"
BTN_SKIP_LINK = "⏭️ Skip"


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_RESUME), KeyboardButton(text=BTN_PORTFOLIO)],
            [KeyboardButton(text=BTN_EXAMPLES), KeyboardButton(text=BTN_WRITE_PROPOSAL)],
            [KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
    )


def settings_menu_kb(notify_qualified_only: bool) -> ReplyKeyboardMarkup:
    """Delivery-mode picker; the current mode is marked with a dot."""
    all_label = BTN_DELIVERY_ALL + ("" if notify_qualified_only else "  •")
    qualified_label = BTN_DELIVERY_QUALIFIED + ("  •" if notify_qualified_only else "")
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=all_label)],
            [KeyboardButton(text=qualified_label)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def resume_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_VIEW_RESUME), KeyboardButton(text=BTN_SET_RESUME)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def portfolio_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LIST_PROJECTS), KeyboardButton(text=BTN_ADD_PROJECT)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def examples_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LIST_EXAMPLES), KeyboardButton(text=BTN_ADD_EXAMPLE)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def delete_button_kb(prefix: str, item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️", callback_data=f"{prefix}:{item_id}")]]
    )


def skip_link_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BTN_SKIP_LINK, callback_data="skip_link")]]
    )

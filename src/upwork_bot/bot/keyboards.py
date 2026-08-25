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
BTN_SETUP = "ℹ️ Setup guide"

BTN_DELIVERY_ALL = "📬 Send all jobs"
BTN_DELIVERY_QUALIFIED = "✅ Send only qualified"

BTN_MAILBOXES = "📮 Mailboxes"
BTN_HOURLY_RATE = "💲 Hourly rate"
BTN_SIGNATURE = "✒️ Signature"
BTN_QUALIFY_PROMPT = "🎯 Qualify prompt"

BTN_VIEW_RESUME = "👁 View resume"
BTN_SET_RESUME = "✏️ Set resume"

BTN_LIST_PROJECTS = "📃 List projects"
BTN_ADD_PROJECT = "➕ Add project"

BTN_LIST_EXAMPLES = "📃 List examples"
BTN_ADD_EXAMPLE = "➕ Add example"

BTN_LIST_MAILBOXES = "📃 List mailboxes"
BTN_ADD_MAILBOX = "➕ Add mailbox"

BTN_VIEW_PROMPT = "👁 View prompt"
BTN_GEN_PROMPT = "✨ Generate prompt"
BTN_SET_PROMPT = "✏️ Set prompt"

BTN_BACK = "⬅️ Back"
BTN_CANCEL = "❌ Cancel"
BTN_SKIP_LINK = "⏭️ Skip"

BTN_START_PARSING = "▶️ Start parsing"
BTN_PAUSE_PARSING = "⏸ Pause parsing"

BTN_QUIET_HOURS = "🌙 Quiet hours"
BTN_TIMEZONE = "🕒 Timezone"

BTN_QUIET_TOGGLE_ON = "🔔 Enable quiet hours"
BTN_QUIET_TOGGLE_OFF = "🔕 Disable quiet hours"
BTN_QUIET_SET_WINDOW = "🕐 Set window"

BTN_TZ_MANUAL = "✍️ Enter manually"

COMMON_TIMEZONES = [
    "Europe/Kyiv",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Moscow",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
    "UTC",
]


def main_menu_kb(parsing_active: bool = True) -> ReplyKeyboardMarkup:
    toggle = BTN_PAUSE_PARSING if parsing_active else BTN_START_PARSING
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_RESUME), KeyboardButton(text=BTN_PORTFOLIO)],
            [KeyboardButton(text=BTN_EXAMPLES), KeyboardButton(text=BTN_WRITE_PROPOSAL)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_SETUP)],
            [KeyboardButton(text=toggle)],
        ],
        resize_keyboard=True,
    )


def settings_menu_kb(notify_qualified_only: bool) -> ReplyKeyboardMarkup:
    """Settings hub: per-user config sections + delivery-mode picker (dot = active)."""
    all_label = BTN_DELIVERY_ALL + ("" if notify_qualified_only else "  •")
    qualified_label = BTN_DELIVERY_QUALIFIED + ("  •" if notify_qualified_only else "")
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MAILBOXES), KeyboardButton(text=BTN_QUALIFY_PROMPT)],
            [KeyboardButton(text=BTN_HOURLY_RATE), KeyboardButton(text=BTN_SIGNATURE)],
            [KeyboardButton(text=BTN_QUIET_HOURS), KeyboardButton(text=BTN_TIMEZONE)],
            [KeyboardButton(text=all_label)],
            [KeyboardButton(text=qualified_label)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def quiet_hours_menu_kb(enabled: bool) -> ReplyKeyboardMarkup:
    toggle = BTN_QUIET_TOGGLE_OFF if enabled else BTN_QUIET_TOGGLE_ON
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=toggle)],
            [KeyboardButton(text=BTN_QUIET_SET_WINDOW), KeyboardButton(text=BTN_TIMEZONE)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def mailboxes_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LIST_MAILBOXES), KeyboardButton(text=BTN_ADD_MAILBOX)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def qualify_prompt_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_VIEW_PROMPT), KeyboardButton(text=BTN_GEN_PROMPT)],
            [KeyboardButton(text=BTN_SET_PROMPT)],
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


def timezone_inline_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=tz, callback_data=f"tz:{tz}")] for tz in COMMON_TIMEZONES]
    rows.append([InlineKeyboardButton(text=BTN_TZ_MANUAL, callback_data="tz_manual")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_folder_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏭️ Use INBOX", callback_data="skip_folder")]]
    )


def regenerate_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Regenerate", callback_data="regen_qualify_prompt")]
        ]
    )

from upwork_bot.bot.keyboards import (
    BTN_ADD_FEED,
    BTN_BACK,
    BTN_CANCEL,
    BTN_EXAMPLES,
    BTN_FEEDS,
    BTN_LIST_FEEDS,
    BTN_PORTFOLIO,
    BTN_RESUME,
    BTN_SKIP_LINK,
    cancel_kb,
    delete_button_kb,
    feeds_menu_kb,
    main_menu_kb,
    skip_link_kb,
)


def _flatten(keyboard) -> list[str]:
    return [button.text for row in keyboard.keyboard for button in row]


def test_main_menu_has_all_four_sections():
    labels = _flatten(main_menu_kb())
    assert set(labels) == {BTN_FEEDS, BTN_RESUME, BTN_PORTFOLIO, BTN_EXAMPLES}


def test_feeds_menu_has_list_add_back():
    labels = _flatten(feeds_menu_kb())
    assert set(labels) == {BTN_LIST_FEEDS, BTN_ADD_FEED, BTN_BACK}


def test_cancel_kb_has_only_cancel():
    labels = _flatten(cancel_kb())
    assert labels == [BTN_CANCEL]


def test_delete_button_kb_encodes_prefix_and_id():
    kb = delete_button_kb("delfeed", 7)
    button = kb.inline_keyboard[0][0]
    assert button.callback_data == "delfeed:7"


def test_skip_link_kb_callback_data():
    kb = skip_link_kb()
    button = kb.inline_keyboard[0][0]
    assert button.text == BTN_SKIP_LINK
    assert button.callback_data == "skip_link"

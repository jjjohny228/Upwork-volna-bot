from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_DELIVERY_ALL,
    BTN_DELIVERY_QUALIFIED,
    BTN_EXAMPLES,
    BTN_PORTFOLIO,
    BTN_RESUME,
    BTN_SETTINGS,
    BTN_SKIP_LINK,
    BTN_WRITE_PROPOSAL,
    cancel_kb,
    delete_button_kb,
    main_menu_kb,
    settings_menu_kb,
    skip_link_kb,
)


def _flatten(keyboard) -> list[str]:
    return [button.text for row in keyboard.keyboard for button in row]


def test_main_menu_has_all_sections():
    labels = _flatten(main_menu_kb())
    assert set(labels) == {
        BTN_RESUME,
        BTN_PORTFOLIO,
        BTN_EXAMPLES,
        BTN_WRITE_PROPOSAL,
        BTN_SETTINGS,
    }


def test_settings_menu_marks_current_mode():
    all_labels = _flatten(settings_menu_kb(notify_qualified_only=False))
    assert any(lbl.startswith(BTN_DELIVERY_ALL) and lbl.endswith("•") for lbl in all_labels)
    assert BTN_BACK in all_labels

    qualified_labels = _flatten(settings_menu_kb(notify_qualified_only=True))
    assert any(
        lbl.startswith(BTN_DELIVERY_QUALIFIED) and lbl.endswith("•") for lbl in qualified_labels
    )


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

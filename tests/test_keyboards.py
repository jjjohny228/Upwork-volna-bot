from upwork_bot.bot.keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_DELIVERY_ALL,
    BTN_DELIVERY_QUALIFIED,
    BTN_EXAMPLES,
    BTN_PORTFOLIO,
    BTN_RESUME,
    BTN_SETTINGS,
    BTN_SETUP,
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
    from upwork_bot.bot.keyboards import BTN_PAUSE_PARSING

    labels = _flatten(main_menu_kb())
    assert {
        BTN_RESUME,
        BTN_PORTFOLIO,
        BTN_EXAMPLES,
        BTN_WRITE_PROPOSAL,
        BTN_SETTINGS,
        BTN_SETUP,
    }.issubset(set(labels))
    # Default state is active -> shows the pause toggle.
    assert BTN_PAUSE_PARSING in labels


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


def test_main_menu_toggle_label_reflects_state():
    from upwork_bot.bot.keyboards import (
        BTN_PAUSE_PARSING,
        BTN_START_PARSING,
        main_menu_kb,
    )

    active_labels = _flatten(main_menu_kb(parsing_active=True))
    assert BTN_PAUSE_PARSING in active_labels
    assert BTN_START_PARSING not in active_labels

    paused_labels = _flatten(main_menu_kb(parsing_active=False))
    assert BTN_START_PARSING in paused_labels
    assert BTN_PAUSE_PARSING not in paused_labels


def test_settings_menu_has_quiet_and_timezone():
    from upwork_bot.bot.keyboards import BTN_QUIET_HOURS, BTN_TIMEZONE, settings_menu_kb

    labels = _flatten(settings_menu_kb(notify_qualified_only=False))
    assert BTN_QUIET_HOURS in labels
    assert BTN_TIMEZONE in labels


def test_quiet_hours_menu_toggle_label():
    from upwork_bot.bot.keyboards import (
        BTN_QUIET_TOGGLE_OFF,
        BTN_QUIET_TOGGLE_ON,
        quiet_hours_menu_kb,
    )

    on_labels = _flatten(quiet_hours_menu_kb(enabled=True))
    assert BTN_QUIET_TOGGLE_OFF in on_labels  # can disable when enabled

    off_labels = _flatten(quiet_hours_menu_kb(enabled=False))
    assert BTN_QUIET_TOGGLE_ON in off_labels  # can enable when disabled


def test_timezone_inline_kb_encodes_zones():
    from upwork_bot.bot.keyboards import COMMON_TIMEZONES, timezone_inline_kb

    kb = timezone_inline_kb()
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert f"tz:{COMMON_TIMEZONES[0]}" in datas
    assert "tz_manual" in datas

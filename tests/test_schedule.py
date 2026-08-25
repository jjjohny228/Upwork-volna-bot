from datetime import UTC, datetime, time

from upwork_bot.db.models import User
from upwork_bot.gmail.schedule import is_parsing_allowed


def _user(**kw) -> User:
    defaults = dict(
        telegram_id=1,
        parsing_active=True,
        quiet_hours_enabled=False,
        timezone=None,
        quiet_start=None,
        quiet_end=None,
    )
    defaults.update(kw)
    return User(**defaults)


def _utc(h: int, m: int = 0) -> datetime:
    return datetime(2026, 8, 25, h, m, tzinfo=UTC)


def test_paused_user_never_parses():
    assert is_parsing_allowed(_user(parsing_active=False), _utc(12)) is False


def test_quiet_disabled_allows():
    assert is_parsing_allowed(_user(parsing_active=True), _utc(3)) is True


def test_missing_timezone_allows_even_if_enabled():
    u = _user(quiet_hours_enabled=True, quiet_start=time(0), quiet_end=time(23, 59))
    assert is_parsing_allowed(u, _utc(12)) is True


def test_same_day_window_blocks_inside():
    # Window 09:00-17:00 UTC; 12:00 UTC is inside -> blocked.
    u = _user(
        quiet_hours_enabled=True,
        timezone="UTC",
        quiet_start=time(9),
        quiet_end=time(17),
    )
    assert is_parsing_allowed(u, _utc(12)) is False
    assert is_parsing_allowed(u, _utc(8)) is True
    assert is_parsing_allowed(u, _utc(17)) is True  # end is exclusive


def test_midnight_wrap_window():
    # Window 23:00-07:00 UTC (wraps midnight).
    u = _user(
        quiet_hours_enabled=True,
        timezone="UTC",
        quiet_start=time(23),
        quiet_end=time(7),
    )
    assert is_parsing_allowed(u, _utc(2)) is False
    assert is_parsing_allowed(u, _utc(23, 30)) is False
    assert is_parsing_allowed(u, _utc(12)) is True


def test_timezone_conversion():
    # Local window 23:00-07:00 in Europe/Kyiv (UTC+3 in August).
    # 21:00 UTC == 00:00 Kyiv -> inside quiet.
    u = _user(
        quiet_hours_enabled=True,
        timezone="Europe/Kyiv",
        quiet_start=time(23),
        quiet_end=time(7),
    )
    assert is_parsing_allowed(u, _utc(21)) is False  # 00:00 local
    assert is_parsing_allowed(u, _utc(9)) is True  # 12:00 local


def test_equal_times_allow():
    u = _user(
        quiet_hours_enabled=True,
        timezone="UTC",
        quiet_start=time(9),
        quiet_end=time(9),
    )
    assert is_parsing_allowed(u, _utc(9)) is True

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from upwork_bot.backup_scheduler import seconds_until_next_run, send_backup_to_admins
from upwork_bot.config import Settings
from upwork_bot.db.backup import BackupError


def test_next_run_later_today():
    now = datetime(2026, 11, 26, 1, 30, tzinfo=UTC)
    assert seconds_until_next_run(now, 3) == 90 * 60


def test_next_run_tomorrow_when_hour_passed():
    now = datetime(2026, 11, 26, 3, 0, tzinfo=UTC)
    assert seconds_until_next_run(now, 3) == 24 * 3600


def _settings(monkeypatch, **env) -> Settings:
    for key, value in {
        "BOT_TOKEN": "t",
        "ADMIN_TELEGRAM_ID": "42",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "OPENAI_API_KEY": "sk",
        **env,
    }.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_backup_recipients_default_to_admin(monkeypatch):
    monkeypatch.delenv("BACKUP_CHAT_IDS", raising=False)
    assert _settings(monkeypatch).backup_recipients == [42]


def test_backup_recipients_parsed(monkeypatch):
    settings = _settings(monkeypatch, BACKUP_CHAT_IDS="1, 2,3")
    assert settings.backup_recipients == [1, 2, 3]


@pytest.mark.asyncio
async def test_sends_dump_to_every_chat():
    bot = AsyncMock()

    async def fake_dump(dest):
        dest.write_bytes(b"dump")

    with patch("upwork_bot.backup_scheduler.dump_database", side_effect=fake_dump):
        await send_backup_to_admins(bot, [1, 2])

    assert [c.args[0] for c in bot.send_document.await_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_one_failed_chat_does_not_block_others():
    bot = AsyncMock()
    bot.send_document.side_effect = [RuntimeError("blocked"), None]

    async def fake_dump(dest):
        dest.write_bytes(b"dump")

    with patch("upwork_bot.backup_scheduler.dump_database", side_effect=fake_dump):
        await send_backup_to_admins(bot, [1, 2])

    assert bot.send_document.await_count == 2


@pytest.mark.asyncio
async def test_dump_failure_notifies_admins():
    bot = AsyncMock()
    with patch("upwork_bot.backup_scheduler.dump_database", side_effect=BackupError("boom <x>")):
        await send_backup_to_admins(bot, [1])

    bot.send_document.assert_not_awaited()
    assert "boom &lt;x&gt;" in bot.send_message.await_args.args[1]

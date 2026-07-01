from upwork_bot.config import Settings


def test_settings_reads_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "42")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.bot_token == "test-token"
    assert settings.admin_telegram_id == 42
    assert settings.poll_interval_seconds == 180

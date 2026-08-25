from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_telegram_id: int
    database_url: str
    openai_api_key: str
    poll_interval_seconds: int = 180

    # Vollna sender + IMAP host stay global (one Vollna, one Gmail IMAP host).
    vollna_sender: str = "info@vollna.com"
    gmail_imap_host: str = "imap.gmail.com"

    # DEPRECATED globals — now per-user (users.hourly_rate/signature_name and the
    # mailboxes table). Kept only so migration 0009 can seed the admin's first
    # mailbox + rate/signature; runtime reads the per-user values instead.
    proposal_signature_name: str = ""
    hourly_rate: float = 0.0
    gmail_address: str = ""
    gmail_app_password: str = ""
    gmail_mailbox: str = "INBOX"


@lru_cache
def get_settings() -> Settings:
    return Settings()

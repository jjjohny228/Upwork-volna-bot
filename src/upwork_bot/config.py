from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    admin_telegram_id: int
    database_url: str
    openai_api_key: str
    poll_interval_seconds: int = 180


@lru_cache
def get_settings() -> Settings:
    return Settings()

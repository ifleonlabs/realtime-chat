"""Application configuration, loaded from environment variables and a .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DB = Path.home() / ".realtime-chat" / "chat.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{DEFAULT_DB.as_posix()}"

    # --- auth -------------------------------------------------------------
    # SECURITY: override AUTH-style secret in production.
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720  # 12 hours

    # --- chat -------------------------------------------------------------
    history_limit: int = 50
    max_message_length: int = 2000

    # --- expiry -----------------------------------------------------------
    # How often the background task deletes expired messages, in seconds.
    cleanup_interval_seconds: int = 60

    @property
    def is_using_default_secret(self) -> bool:
        return self.jwt_secret == "dev-only-insecure-secret-change-me"


def get_settings() -> Settings:
    """Return a fresh Settings instance (re-reads env each call)."""
    return Settings()

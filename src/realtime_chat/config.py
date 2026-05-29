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

    # How many recent messages to send a client when it joins a room.
    history_limit: int = 50

    # Maximum accepted length of a single chat message.
    max_message_length: int = 2000


def get_settings() -> Settings:
    """Return a fresh Settings instance (re-reads env each call)."""
    return Settings()

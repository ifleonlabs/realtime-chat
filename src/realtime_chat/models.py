"""Database models (SQLModel tables)."""

# No `from __future__ import annotations` — kept consistent with the series'
# SQLModel modules (evaluated annotations are required for relationships).

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Message(SQLModel, table=True):
    """A single chat message, persisted so history survives restarts."""

    id: Optional[int] = Field(default=None, primary_key=True)
    room: str = Field(index=True)
    username: str
    content: str
    created_at: datetime = Field(default_factory=utcnow)

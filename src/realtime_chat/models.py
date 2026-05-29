"""Database models (SQLModel tables): users, rooms, memberships, messages."""

# No `from __future__ import annotations` — SQLModel needs evaluated annotations.

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=utcnow)


class Room(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    description: str = ""
    owner_id: int = Field(foreign_key="user.id", index=True)
    is_private: bool = False
    # Required to join a private room; empty for public rooms.
    join_code: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    # Rolling message expiry: every message in this room is deleted this many
    # seconds after it is posted (max 24h). The room itself persists.
    message_ttl_seconds: int = 86_400


class RoomMembership(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    room_id: int = Field(foreign_key="room.id", index=True)
    joined_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", index=True)
    user_id: int = Field(foreign_key="user.id")
    username: str  # denormalized for easy display
    content: str
    created_at: datetime = Field(default_factory=utcnow)
    # When this message rolls off and is deleted (created_at + room TTL).
    expires_at: datetime = Field(default_factory=utcnow, index=True)

"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Allowed room lifetimes (label -> hours; None = never expires).
LIFETIME_HOURS: dict[str, Optional[int]] = {
    "1h": 1,
    "24h": 24,
    "7d": 24 * 7,
    "never": None,
}
Lifetime = Literal["1h", "24h", "7d", "never"]


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(..., min_length=6, max_length=128)


class UserRead(BaseModel):
    id: int
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    description: str = Field("", max_length=200)
    is_private: bool = False
    lifetime: Lifetime = "24h"


class JoinRequest(BaseModel):
    code: str = ""


class RoomRead(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    is_private: bool
    owner_username: str
    member_count: int
    created_at: datetime
    expires_at: Optional[datetime]
    is_owner: bool
    is_member: bool
    # Only populated for the owner of a private room, so they can share it.
    join_code: Optional[str] = None

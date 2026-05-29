"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Messages roll off after a per-room TTL. The hard maximum is 24 hours.
MAX_TTL_MINUTES = 24 * 60  # 1440


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
    # How long each message lives before rolling off, in minutes (max 24h).
    ttl_minutes: int = Field(MAX_TTL_MINUTES, ge=1, le=MAX_TTL_MINUTES)


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
    # Each message in this room rolls off after this many seconds.
    message_ttl_seconds: int
    is_owner: bool
    is_member: bool
    # Only populated for the owner of a private room, so they can share it.
    join_code: Optional[str] = None

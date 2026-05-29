"""Message service: persistence, rolling expiry, and history retrieval."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, delete, select

from .models import Message


def _aware(dt: datetime) -> datetime:
    """Treat naive datetimes (from SQLite) as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def save(session: Session, room_id: int, user_id: int, username: str, content: str, ttl_seconds: int) -> Message:
    now = datetime.now(timezone.utc)
    message = Message(
        room_id=room_id,
        user_id=user_id,
        username=username,
        content=content,
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def recent(session: Session, room_id: int, limit: int) -> list[Message]:
    """Return the last ``limit`` non-expired messages in a room, oldest-first."""
    now = datetime.now(timezone.utc)
    rows = session.exec(
        select(Message)
        .where(Message.room_id == room_id, Message.expires_at > now)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def purge_expired(session: Session, now: datetime | None = None) -> int:
    """Delete messages whose expiry has passed. Returns how many were removed."""
    now = now or datetime.now(timezone.utc)
    result = session.exec(delete(Message).where(Message.expires_at <= now))
    session.commit()
    return result.rowcount or 0


def payload(message: Message) -> dict:
    return {
        "type": "message",
        "username": message.username,
        "content": message.content,
        "created_at": _aware(message.created_at).isoformat(),
        "expires_at": _aware(message.expires_at).isoformat(),
    }

"""Message service: persistence, rolling expiry, reactions, edits, replies."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, delete, select

from .models import Message


def _aware(dt: datetime) -> datetime:
    """Treat naive datetimes (from SQLite) as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _excerpt(content: str) -> str:
    """A short preview used when quoting a message in a reply."""
    if content.startswith("{"):
        try:
            o = json.loads(content)
            if o.get("_media"):
                return f"📎 {o['_media'].get('name', 'file')}"
        except json.JSONDecodeError:
            pass
    return content[:80]


def get(session: Session, message_id: int) -> Optional[Message]:
    return session.get(Message, message_id)


def save(
    session: Session,
    room_id: int,
    user_id: int,
    username: str,
    content: str,
    ttl_seconds: int,
    reply_to: Optional[Message] = None,
) -> Message:
    now = datetime.now(timezone.utc)
    message = Message(
        room_id=room_id,
        user_id=user_id,
        username=username,
        content=content,
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
        reply_to_username=reply_to.username if reply_to else None,
        reply_to_excerpt=_excerpt(reply_to.content) if reply_to else None,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def edit(session: Session, message: Message, content: str) -> Message:
    message.content = content
    message.edited = True
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def remove(session: Session, message: Message) -> None:
    session.delete(message)
    session.commit()


def toggle_reaction(session: Session, message: Message, username: str, emoji: str) -> dict:
    """Add or remove ``username``'s ``emoji`` reaction; returns the new map."""
    data: dict[str, list[str]] = json.loads(message.reactions or "{}")
    users = set(data.get(emoji, []))
    if username in users:
        users.discard(username)
    else:
        users.add(username)
    if users:
        data[emoji] = sorted(users)
    else:
        data.pop(emoji, None)
    message.reactions = json.dumps(data)
    session.add(message)
    session.commit()
    return data


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
    reply = None
    if message.reply_to_username is not None:
        reply = {"username": message.reply_to_username, "excerpt": message.reply_to_excerpt or ""}
    return {
        "type": "message",
        "id": message.id,
        "username": message.username,
        "content": message.content,
        "created_at": _aware(message.created_at).isoformat(),
        "expires_at": _aware(message.expires_at).isoformat(),
        "edited": message.edited,
        "reactions": json.loads(message.reactions or "{}"),
        "reply": reply,
    }

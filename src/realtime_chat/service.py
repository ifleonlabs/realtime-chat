"""Message persistence and history retrieval over a database session."""

from __future__ import annotations

from sqlmodel import Session, func, select

from .models import Message


def save_message(session: Session, room: str, username: str, content: str) -> Message:
    message = Message(room=room, username=username, content=content)
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def recent_messages(session: Session, room: str, limit: int) -> list[Message]:
    """Return the last ``limit`` messages in ``room``, oldest-first."""
    rows = session.exec(
        select(Message)
        .where(Message.room == room)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def list_rooms(session: Session) -> list[tuple[str, int]]:
    """Return (room, message_count) pairs, busiest first."""
    rows = session.exec(
        select(Message.room, func.count(Message.id))
        .group_by(Message.room)
        .order_by(func.count(Message.id).desc())
    ).all()
    return [(room, count) for room, count in rows]


def message_payload(message: Message) -> dict:
    """Serialize a message for sending over the wire."""
    return {
        "type": "message",
        "username": message.username,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }

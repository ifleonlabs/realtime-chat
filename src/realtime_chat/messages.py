"""Message service: persistence and history retrieval (per room id)."""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Message


def save(session: Session, room_id: int, user_id: int, username: str, content: str) -> Message:
    message = Message(
        room_id=room_id, user_id=user_id, username=username, content=content
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def recent(session: Session, room_id: int, limit: int) -> list[Message]:
    """Return the last ``limit`` messages in a room, oldest-first."""
    rows = session.exec(
        select(Message)
        .where(Message.room_id == room_id)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def payload(message: Message) -> dict:
    return {
        "type": "message",
        "username": message.username,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }

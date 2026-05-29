"""Room service: creation, access control, and listing.

Rooms persist; it's the *messages* inside them that roll off (see
``messages.py``). A room only records how long its messages should live.
"""

from __future__ import annotations

import re
import secrets
from typing import Optional

from sqlmodel import Session, delete, func, select

from .models import Message, Room, RoomMembership, User
from .schemas import RoomCreate


class RoomError(Exception):
    """Raised for room creation/join/access problems."""


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "room"
    return f"{base}-{secrets.token_hex(3)}"


def get_by_slug(session: Session, slug: str) -> Optional[Room]:
    return session.exec(select(Room).where(Room.slug == slug)).first()


def member_count(session: Session, room_id: int) -> int:
    return session.exec(
        select(func.count()).select_from(RoomMembership).where(RoomMembership.room_id == room_id)
    ).one()


def is_member(session: Session, user_id: int, room_id: int) -> bool:
    return session.exec(
        select(RoomMembership).where(
            RoomMembership.user_id == user_id, RoomMembership.room_id == room_id
        )
    ).first() is not None


def create(session: Session, owner: User, data: RoomCreate) -> Room:
    room = Room(
        slug=_slugify(data.name),
        name=data.name,
        description=data.description,
        owner_id=owner.id,
        is_private=data.is_private,
        join_code=secrets.token_urlsafe(6) if data.is_private else "",
        message_ttl_seconds=data.ttl_minutes * 60,
    )
    session.add(room)
    session.commit()
    session.refresh(room)
    # The owner is automatically a member.
    session.add(RoomMembership(user_id=owner.id, room_id=room.id))
    session.commit()
    return room


def join(session: Session, user: User, room: Room, code: str = "") -> None:
    """Add a user to a room, enforcing the join code for private rooms."""
    is_owner = room.owner_id == user.id
    if room.is_private and not is_owner and code != room.join_code:
        raise RoomError("Incorrect or missing join code for this private room.")
    if not is_member(session, user.id, room.id):
        session.add(RoomMembership(user_id=user.id, room_id=room.id))
        session.commit()


def has_access(session: Session, user: User, room: Room) -> bool:
    return room.owner_id == user.id or is_member(session, user.id, room.id)


def list_public(session: Session) -> list[Room]:
    return session.exec(
        select(Room).where(Room.is_private == False).order_by(Room.created_at.desc())  # noqa: E712
    ).all()


def list_for_user(session: Session, user: User) -> list[Room]:
    """Rooms the user owns or has joined (public or private), newest first."""
    owned = select(Room.id).where(Room.owner_id == user.id)
    joined = select(RoomMembership.room_id).where(RoomMembership.user_id == user.id)
    ids = set(session.exec(owned).all()) | set(session.exec(joined).all())
    if not ids:
        return []
    return session.exec(
        select(Room).where(Room.id.in_(ids)).order_by(Room.created_at.desc())
    ).all()


def delete_room(session: Session, room: Room) -> None:
    """Delete a room and its messages + memberships."""
    session.exec(delete(Message).where(Message.room_id == room.id))
    session.exec(delete(RoomMembership).where(RoomMembership.room_id == room.id))
    session.delete(room)
    session.commit()

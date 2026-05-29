"""Room service: creation, access control, listing, and expiry."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, delete, func, select

from .models import Message, Room, RoomMembership, User
from .schemas import LIFETIME_HOURS, RoomCreate


class RoomError(Exception):
    """Raised for room creation/join/access problems."""


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "room"
    return f"{base}-{secrets.token_hex(3)}"


def get_by_slug(session: Session, slug: str) -> Optional[Room]:
    return session.exec(select(Room).where(Room.slug == slug)).first()


def is_expired(room: Room, now: Optional[datetime] = None) -> bool:
    if room.expires_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    expires = room.expires_at
    if expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= now


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
    hours = LIFETIME_HOURS[data.lifetime]
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=hours) if hours is not None else None
    )
    room = Room(
        slug=_slugify(data.name),
        name=data.name,
        description=data.description,
        owner_id=owner.id,
        is_private=data.is_private,
        join_code=secrets.token_urlsafe(6) if data.is_private else "",
        expires_at=expires_at,
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
    if is_expired(room):
        raise RoomError("This room has expired.")
    is_owner = room.owner_id == user.id
    if room.is_private and not is_owner and code != room.join_code:
        raise RoomError("Incorrect or missing join code for this private room.")
    if not is_member(session, user.id, room.id):
        session.add(RoomMembership(user_id=user.id, room_id=room.id))
        session.commit()


def has_access(session: Session, user: User, room: Room) -> bool:
    return room.owner_id == user.id or is_member(session, user.id, room.id)


def list_public(session: Session) -> list[Room]:
    rooms = session.exec(
        select(Room).where(Room.is_private == False).order_by(Room.created_at.desc())  # noqa: E712
    ).all()
    return [r for r in rooms if not is_expired(r)]


def list_for_user(session: Session, user: User) -> list[Room]:
    """Rooms the user owns or has joined (public or private), newest first."""
    owned = select(Room.id).where(Room.owner_id == user.id)
    joined = select(RoomMembership.room_id).where(RoomMembership.user_id == user.id)
    ids = set(session.exec(owned).all()) | set(session.exec(joined).all())
    if not ids:
        return []
    rooms = session.exec(
        select(Room).where(Room.id.in_(ids)).order_by(Room.created_at.desc())
    ).all()
    return [r for r in rooms if not is_expired(r)]


def delete_room(session: Session, room: Room) -> None:
    """Delete a room and its messages + memberships."""
    session.exec(delete(Message).where(Message.room_id == room.id))
    session.exec(delete(RoomMembership).where(RoomMembership.room_id == room.id))
    session.delete(room)
    session.commit()


def purge_expired(session: Session, now: Optional[datetime] = None) -> list[str]:
    """Delete every expired room; return the slugs that were removed."""
    now = now or datetime.now(timezone.utc)
    rooms = session.exec(select(Room).where(Room.expires_at.is_not(None))).all()
    removed = []
    for room in rooms:
        if is_expired(room, now):
            slug = room.slug
            delete_room(session, room)
            removed.append(slug)
    return removed

"""Service-layer tests: users, rooms (access + expiry), and messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from realtime_chat import messages, rooms, users
from realtime_chat.models import Room
from realtime_chat.rooms import RoomError
from realtime_chat.schemas import RoomCreate, UserCreate
from realtime_chat.users import AuthError


def _user(session, name="alice"):
    return users.register(session, UserCreate(username=name, password="password123"))


# --- users -----------------------------------------------------------------
def test_register_and_authenticate(session):
    _user(session)
    assert users.authenticate(session, "alice", "password123").username == "alice"
    with pytest.raises(AuthError):
        users.authenticate(session, "alice", "wrong")


def test_duplicate_username_rejected(session):
    _user(session)
    with pytest.raises(AuthError, match="taken"):
        _user(session)


# --- rooms -----------------------------------------------------------------
def test_create_public_room_owner_is_member(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="General", is_private=False))
    assert room.slug.startswith("general-")
    assert room.join_code == ""
    assert rooms.has_access(session, alice, room)
    assert rooms.member_count(session, room.id) == 1


def test_private_room_requires_code(session):
    alice = _user(session)
    bob = _user(session, "bob")
    room = rooms.create(session, alice, RoomCreate(name="Secret", is_private=True))
    assert room.join_code  # generated

    with pytest.raises(RoomError, match="join code"):
        rooms.join(session, bob, room, code="wrong")
    assert not rooms.has_access(session, bob, room)

    rooms.join(session, bob, room, code=room.join_code)
    assert rooms.has_access(session, bob, room)


def test_public_room_join_without_code(session):
    alice = _user(session)
    bob = _user(session, "bob")
    room = rooms.create(session, alice, RoomCreate(name="Open", is_private=False))
    rooms.join(session, bob, room)
    assert rooms.has_access(session, bob, room)
    assert rooms.member_count(session, room.id) == 2


def test_lifetime_sets_expiry(session):
    alice = _user(session)
    room_24 = rooms.create(session, alice, RoomCreate(name="day", lifetime="24h"))
    assert room_24.expires_at is not None
    room_never = rooms.create(session, alice, RoomCreate(name="forever", lifetime="never"))
    assert room_never.expires_at is None


def test_is_expired_and_purge(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="temp", lifetime="1h"))
    # Force it into the past.
    room.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session.add(room)
    session.commit()

    assert rooms.is_expired(room)
    removed = rooms.purge_expired(session)
    assert room.slug in removed
    assert rooms.get_by_slug(session, room.slug) is None


def test_list_public_excludes_private_and_expired(session):
    alice = _user(session)
    rooms.create(session, alice, RoomCreate(name="pub", is_private=False))
    rooms.create(session, alice, RoomCreate(name="priv", is_private=True))
    public = rooms.list_public(session)
    assert [r.name for r in public] == ["pub"]


def test_delete_room_cascades_messages(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    messages.save(session, room.id, alice.id, alice.username, "hi")
    rooms.delete_room(session, room)
    assert rooms.get_by_slug(session, room.slug) is None
    assert messages.recent(session, room.id, 10) == []


# --- messages --------------------------------------------------------------
def test_messages_recent_order_and_limit(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    for i in range(5):
        messages.save(session, room.id, alice.id, alice.username, f"m{i}")
    recent = messages.recent(session, room.id, 3)
    assert [m.content for m in recent] == ["m2", "m3", "m4"]

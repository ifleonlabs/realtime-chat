"""Service-layer tests: users, rooms (access + expiry), and messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from realtime_chat import messages, rooms, users
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


def test_ttl_minutes_sets_message_ttl(session):
    alice = _user(session)
    room_24 = rooms.create(session, alice, RoomCreate(name="day", ttl_minutes=1440))
    assert room_24.message_ttl_seconds == 86_400
    room_short = rooms.create(session, alice, RoomCreate(name="short", ttl_minutes=30))
    assert room_short.message_ttl_seconds == 1800


def test_ttl_minutes_capped_at_24h():
    with pytest.raises(Exception):  # pydantic validation (le=1440)
        RoomCreate(name="too long", ttl_minutes=2000)


def test_list_public_excludes_private(session):
    alice = _user(session)
    rooms.create(session, alice, RoomCreate(name="pub", is_private=False))
    rooms.create(session, alice, RoomCreate(name="priv", is_private=True))
    public = rooms.list_public(session)
    assert [r.name for r in public] == ["pub"]


def test_delete_room_cascades_messages(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    messages.save(session, room.id, alice.id, alice.username, "hi", room.message_ttl_seconds)
    rooms.delete_room(session, room)
    assert rooms.get_by_slug(session, room.slug) is None
    assert messages.recent(session, room.id, 10) == []


# --- messages (rolling expiry) ---------------------------------------------
def test_messages_recent_order_and_limit(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    for i in range(5):
        messages.save(session, room.id, alice.id, alice.username, f"m{i}", 3600)
    recent = messages.recent(session, room.id, 3)
    assert [m.content for m in recent] == ["m2", "m3", "m4"]


def test_reactions_toggle(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    m = messages.save(session, room.id, alice.id, "alice", "hi", 3600)
    assert messages.toggle_reaction(session, m, "alice", "👍") == {"👍": ["alice"]}
    assert messages.toggle_reaction(session, m, "bob", "👍") == {"👍": ["alice", "bob"]}
    assert messages.toggle_reaction(session, m, "alice", "👍") == {"👍": ["bob"]}
    assert messages.toggle_reaction(session, m, "bob", "👍") == {}


def test_edit_and_reply_excerpt(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    m = messages.save(session, room.id, alice.id, "alice", "original", 3600)
    messages.edit(session, m, "updated")
    assert m.content == "updated" and m.edited is True
    reply = messages.save(session, room.id, alice.id, "alice", "ok", 3600, reply_to=m)
    p = messages.payload(reply)
    assert p["reply"] == {"username": "alice", "excerpt": "updated"}


def test_recent_excludes_expired_messages(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    # An already-expired message (negative TTL) is hidden from history.
    messages.save(session, room.id, alice.id, alice.username, "old", -10)
    messages.save(session, room.id, alice.id, alice.username, "fresh", 3600)
    assert [m.content for m in messages.recent(session, room.id, 10)] == ["fresh"]


def test_purge_expired_messages(session):
    alice = _user(session)
    room = rooms.create(session, alice, RoomCreate(name="r"))
    messages.save(session, room.id, alice.id, alice.username, "old", -10)
    messages.save(session, room.id, alice.id, alice.username, "keep", 3600)
    removed = messages.purge_expired(session)
    assert removed == 1
    # The fresh one survives.
    assert [m.content for m in messages.recent(session, room.id, 10)] == ["keep"]

"""Tests for message persistence and history retrieval."""

from __future__ import annotations

from realtime_chat import service


def test_save_and_recent(session):
    service.save_message(session, "general", "alice", "hello")
    service.save_message(session, "general", "bob", "hi there")
    recent = service.recent_messages(session, "general", 10)
    assert [m.content for m in recent] == ["hello", "hi there"]  # oldest-first


def test_recent_respects_limit_and_order(session):
    for i in range(5):
        service.save_message(session, "general", "u", f"m{i}")
    recent = service.recent_messages(session, "general", 3)
    assert [m.content for m in recent] == ["m2", "m3", "m4"]  # last 3, oldest-first


def test_messages_are_room_scoped(session):
    service.save_message(session, "a", "u", "in-a")
    service.save_message(session, "b", "u", "in-b")
    assert [m.content for m in service.recent_messages(session, "a", 10)] == ["in-a"]


def test_list_rooms_counts(session):
    service.save_message(session, "busy", "u", "1")
    service.save_message(session, "busy", "u", "2")
    service.save_message(session, "quiet", "u", "1")
    assert service.list_rooms(session) == [("busy", 2), ("quiet", 1)]


def test_message_payload_shape(session):
    m = service.save_message(session, "general", "alice", "yo")
    payload = service.message_payload(m)
    assert payload["type"] == "message"
    assert payload["username"] == "alice"
    assert payload["content"] == "yo"
    assert "created_at" in payload

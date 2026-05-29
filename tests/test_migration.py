"""Regression test: a database created by an older version is migrated in place."""

from __future__ import annotations

from sqlmodel import Session

from realtime_chat import db, messages, rooms, users
from realtime_chat.schemas import RoomCreate, UserCreate


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def test_init_db_migrates_old_schema(tmp_path, monkeypatch):
    path = (tmp_path / "old.db").as_posix()
    monkeypatch.setenv("CHAT_DATABASE_URL", f"sqlite:///{path}")
    db.reset_engine()
    engine = db.get_engine()

    # Simulate the oldest schema mix this app has seen:
    #   - room from v0.2.0 (has expires_at, not message_ttl_seconds)
    #   - message from v0.1.0 (free-form `room` string; no room_id/user_id/expires_at)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE room (id INTEGER PRIMARY KEY, slug TEXT, name TEXT, "
            "description TEXT, owner_id INTEGER, is_private BOOLEAN, join_code TEXT, "
            "created_at DATETIME, expires_at DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE message (id INTEGER PRIMARY KEY, room TEXT, "
            "username TEXT, content TEXT, created_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO room (slug, name, description, owner_id, is_private, join_code, created_at) "
            "VALUES ('old-1', 'Old', '', 1, 0, '', '2026-01-01 00:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO message (room, username, content, created_at) "
            "VALUES ('general', 'bob', 'hello', '2026-01-01 00:00:00')"
        )

    db.init_db()  # creates the new tables and migrates the old ones

    with engine.begin() as conn:
        assert "message_ttl_seconds" in _columns(conn, "room")
        assert {"room_id", "user_id", "expires_at"} <= _columns(conn, "message")
        assert conn.exec_driver_sql("SELECT message_ttl_seconds FROM room").scalar() == 86400

    # The app must work end-to-end on the migrated DB.
    with Session(engine) as session:
        alice = users.register(session, UserCreate(username="alice", password="password123"))
        room = rooms.create(session, alice, RoomCreate(name="Fresh"))
        messages.save(session, room.id, alice.id, alice.username, "hi", room.message_ttl_seconds)
        recent = messages.recent(session, room.id, 50)
        assert [m.content for m in recent] == ["hi"]  # legacy orphan row excluded

    db.reset_engine()

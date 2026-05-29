"""Regression test: a database created by an older version is migrated in place."""

from __future__ import annotations

from realtime_chat import db


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def test_init_db_migrates_old_schema(tmp_path, monkeypatch):
    path = (tmp_path / "old.db").as_posix()
    monkeypatch.setenv("CHAT_DATABASE_URL", f"sqlite:///{path}")
    db.reset_engine()
    engine = db.get_engine()

    # Simulate the v0.2.0 schema: room has expires_at (not message_ttl_seconds),
    # and message has no expires_at column.
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE room (id INTEGER PRIMARY KEY, slug TEXT, name TEXT, "
            "description TEXT, owner_id INTEGER, is_private BOOLEAN, join_code TEXT, "
            "created_at DATETIME, expires_at DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE message (id INTEGER PRIMARY KEY, room_id INTEGER, "
            "user_id INTEGER, username TEXT, content TEXT, created_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO room (slug, name, description, owner_id, is_private, join_code, created_at) "
            "VALUES ('old-1', 'Old', '', 1, 0, '', '2026-01-01 00:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO message (room_id, user_id, username, content, created_at) "
            "VALUES (1, 1, 'bob', 'hello', '2026-01-01 00:00:00')"
        )

    db.init_db()  # creates the new tables and migrates the old ones

    with engine.begin() as conn:
        assert "message_ttl_seconds" in _columns(conn, "room")
        assert "expires_at" in _columns(conn, "message")
        # The migrated column has the default and the backfill applied.
        ttl = conn.exec_driver_sql("SELECT message_ttl_seconds FROM room").scalar()
        assert ttl == 86400
        exp = conn.exec_driver_sql("SELECT expires_at FROM message").scalar()
        assert exp is not None  # backfilled to created_at + 1 day

    db.reset_engine()

"""Database engine and session management (lazy + resettable for tests)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            path = url.replace("sqlite:///", "", 1)
            if path and path != ":memory:":
                Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, connect_args=connect_args)
    return _engine


def init_db() -> None:
    """Create all tables, then run lightweight column migrations. Idempotent."""
    from . import models  # noqa: F401  (registers tables on the metadata)

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _migrate_sqlite(engine)


def _migrate_sqlite(engine: Engine) -> None:
    """Add columns introduced in newer versions to a pre-existing SQLite DB.

    ``create_all`` never alters existing tables, so a database created by an
    earlier version is missing the newer columns. We add them in place (keeping
    existing rows) rather than forcing the user to delete their database.
    """
    if engine.dialect.name != "sqlite":
        return

    def columns(conn, table: str) -> set[str]:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}

    with engine.begin() as conn:
        room_cols = columns(conn, "room")
        # A non-empty set without the new column means an old schema.
        if room_cols and "message_ttl_seconds" not in room_cols:
            conn.exec_driver_sql(
                "ALTER TABLE room ADD COLUMN message_ttl_seconds INTEGER NOT NULL DEFAULT 86400"
            )

        # The message table changed shape across versions:
        #   v0.1.0: (room TEXT NOT NULL, username, content, created_at)
        #   v0.2.0: room -> room_id + user_id foreign keys
        #   v0.3.0: + expires_at
        message_cols = columns(conn, "message")

        # A legacy v0.1.0 table still has the free-form `room` column, which is
        # NOT NULL and indexed — so new inserts (which only set room_id) fail.
        # Those rows reference room *names* that don't exist in the new model
        # and can't be mapped, so rebuild the table cleanly. (Only triggers for
        # v0.1.0-lineage databases; v0.2.0+ message tables keep their rows.)
        if "room" in message_cols:
            from .models import Message

            conn.exec_driver_sql("DROP TABLE message")
            Message.__table__.create(bind=conn, checkfirst=True)
            message_cols = columns(conn, "message")

        if message_cols:
            # Otherwise just add any columns introduced after this DB was made.
            if "room_id" not in message_cols:
                conn.exec_driver_sql("ALTER TABLE message ADD COLUMN room_id INTEGER")
            if "user_id" not in message_cols:
                conn.exec_driver_sql("ALTER TABLE message ADD COLUMN user_id INTEGER")
            if "expires_at" not in message_cols:
                conn.exec_driver_sql("ALTER TABLE message ADD COLUMN expires_at DATETIME")
                conn.exec_driver_sql(
                    "UPDATE message SET expires_at = datetime(created_at, '+1 day') "
                    "WHERE expires_at IS NULL"
                )


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def reset_engine() -> None:
    """Dispose the engine so the next call rebuilds it (used by tests)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None

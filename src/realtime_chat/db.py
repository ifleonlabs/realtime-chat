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

        message_cols = columns(conn, "message")
        if message_cols and "expires_at" not in message_cols:
            conn.exec_driver_sql("ALTER TABLE message ADD COLUMN expires_at DATETIME")
            # Backfill: keep old messages for 24h from when they were sent.
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

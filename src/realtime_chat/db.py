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
    """Create all tables. Safe to call repeatedly."""
    from . import models  # noqa: F401  (registers tables on the metadata)

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def reset_engine() -> None:
    """Dispose the engine so the next call rebuilds it (used by tests)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None

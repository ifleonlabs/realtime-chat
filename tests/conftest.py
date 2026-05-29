"""Shared fixtures: isolated temp database per test."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from realtime_chat import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = (tmp_path / "test.db").as_posix()
    monkeypatch.setenv("CHAT_DATABASE_URL", f"sqlite:///{db_path}")
    db.reset_engine()
    db.init_db()
    yield
    db.reset_engine()


@pytest.fixture
def session():
    with Session(db.get_engine()) as s:
        yield s


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from realtime_chat.web.app import app

    with TestClient(app) as c:
        yield c

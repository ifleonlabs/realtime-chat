"""Shared fixtures: isolated temp database + fixed JWT secret per test."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from realtime_chat import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = (tmp_path / "test.db").as_posix()
    monkeypatch.setenv("CHAT_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("CHAT_JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
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


def _register(client, username="alice", password="password123"):
    res = client.post("/api/auth/register", json={"username": username, "password": password})
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


@pytest.fixture
def auth(client):
    """Return a helper that creates users and returns auth headers."""
    def make(username="alice", password="password123"):
        token = _register(client, username, password)
        return {"Authorization": f"Bearer {token}"}
    return make

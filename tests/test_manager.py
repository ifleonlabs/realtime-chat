"""Unit tests for the in-memory ConnectionManager (async, with a fake socket)."""

from __future__ import annotations

from realtime_chat.manager import ConnectionManager


class FakeWS:
    def __init__(self) -> None:
        self.accepted = False
        self.closed = False
        self.sent: list = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed = True


async def test_connect_and_presence():
    mgr = ConnectionManager()
    ws = FakeWS()
    await mgr.connect("general", ws, "alice")
    assert ws.accepted and mgr.count("general") == 1
    assert mgr.usernames("general") == ["alice"]


async def test_broadcast_reaches_all():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    await mgr.connect("r", a, "alice")
    await mgr.connect("r", b, "bob")
    await mgr.broadcast("r", {"x": 1})
    assert a.sent == [{"x": 1}] and b.sent == [{"x": 1}]


async def test_disconnect_cleans_empty_room():
    mgr = ConnectionManager()
    ws = FakeWS()
    await mgr.connect("r", ws, "alice")
    mgr.disconnect("r", ws)
    assert mgr.count("r") == 0 and mgr.usernames("r") == []


async def test_close_room_notifies_and_disconnects():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    await mgr.connect("r", a, "alice")
    await mgr.connect("r", b, "bob")
    await mgr.close_room("r", {"type": "system", "content": "expired"})
    assert a.closed and b.closed
    assert {"type": "system", "content": "expired"} in a.sent
    assert mgr.count("r") == 0


async def test_rooms_isolated():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    await mgr.connect("a", a, "alice")
    await mgr.connect("b", b, "bob")
    await mgr.broadcast("a", {"x": 1})
    assert a.sent == [{"x": 1}] and b.sent == []

"""Unit tests for the in-memory ConnectionManager (async, with a fake socket)."""

from __future__ import annotations

from realtime_chat.manager import ConnectionManager


class FakeWS:
    """A minimal stand-in for a Starlette WebSocket."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data) -> None:
        self.sent.append(data)


async def test_connect_accepts_and_registers():
    mgr = ConnectionManager()
    ws = FakeWS()
    await mgr.connect("general", ws, "alice")
    assert ws.accepted
    assert mgr.count("general") == 1
    assert mgr.usernames("general") == ["alice"]


async def test_broadcast_reaches_all_connections():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    await mgr.connect("room", a, "alice")
    await mgr.connect("room", b, "bob")

    await mgr.broadcast("room", {"type": "message", "content": "hi"})
    assert {"type": "message", "content": "hi"} in a.sent
    assert {"type": "message", "content": "hi"} in b.sent


async def test_disconnect_removes_and_cleans_empty_room():
    mgr = ConnectionManager()
    ws = FakeWS()
    await mgr.connect("room", ws, "alice")
    mgr.disconnect("room", ws)
    assert mgr.count("room") == 0
    assert mgr.usernames("room") == []  # room entry dropped, no error


async def test_usernames_are_distinct_and_sorted():
    mgr = ConnectionManager()
    for name in ["bob", "alice", "bob"]:
        await mgr.connect("room", FakeWS(), name)
    assert mgr.usernames("room") == ["alice", "bob"]


async def test_broadcast_skips_broken_connection():
    mgr = ConnectionManager()
    good = FakeWS()

    class Broken(FakeWS):
        async def send_json(self, data):
            raise RuntimeError("socket closed")

    await mgr.connect("room", good, "good")
    await mgr.connect("room", Broken(), "broken")
    # Should not raise even though one connection errors.
    await mgr.broadcast("room", {"type": "system", "content": "ping"})
    assert len(good.sent) == 1


async def test_rooms_are_isolated():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    await mgr.connect("room-a", a, "alice")
    await mgr.connect("room-b", b, "bob")
    await mgr.broadcast("room-a", {"x": 1})
    assert a.sent == [{"x": 1}]
    assert b.sent == []

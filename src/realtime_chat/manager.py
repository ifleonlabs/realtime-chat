"""Tracks live WebSocket connections per room and broadcasts to them.

This is the in-memory real-time layer (separate from the database, which only
stores message history). One ``ConnectionManager`` instance is shared by the
app for the life of the process. Rooms are keyed by their slug.
"""

from __future__ import annotations

from typing import Any, Protocol


class WSLike(Protocol):
    """The subset of WebSocket behavior the manager relies on."""

    async def accept(self) -> None: ...
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        # room slug -> {connection: username}
        self._rooms: dict[str, dict[WSLike, str]] = {}

    async def connect(self, room: str, websocket: WSLike, username: str) -> None:
        await websocket.accept()
        self._rooms.setdefault(room, {})[websocket] = username

    def disconnect(self, room: str, websocket: WSLike) -> None:
        connections = self._rooms.get(room)
        if connections and websocket in connections:
            del connections[websocket]
            if not connections:
                del self._rooms[room]

    def usernames(self, room: str) -> list[str]:
        return sorted(set(self._rooms.get(room, {}).values()))

    def count(self, room: str) -> int:
        return len(self._rooms.get(room, {}))

    async def broadcast(self, room: str, payload: dict) -> None:
        """Send ``payload`` (as JSON) to every connection in ``room``."""
        for websocket in list(self._rooms.get(room, {}).keys()):
            try:
                await websocket.send_json(payload)
            except Exception:
                pass

    async def close_room(self, room: str, payload: dict | None = None) -> None:
        """Notify and disconnect everyone in a room (e.g. when it expires)."""
        connections = list(self._rooms.get(room, {}).keys())
        for websocket in connections:
            try:
                if payload is not None:
                    await websocket.send_json(payload)
                await websocket.close()
            except Exception:
                pass
        self._rooms.pop(room, None)

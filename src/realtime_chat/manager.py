"""Tracks live WebSocket connections per room and broadcasts to them.

This is the in-memory real-time layer (separate from the database, which only
stores message history). One ``ConnectionManager`` instance is shared by the
app for the life of the process.
"""

from __future__ import annotations

from typing import Any, Protocol


class WSLike(Protocol):
    """The subset of WebSocket behavior the manager relies on.

    Declaring it as a Protocol lets tests pass a lightweight fake instead of a
    real Starlette WebSocket.
    """

    async def accept(self) -> None: ...
    async def send_json(self, data: Any) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        # room name -> {connection: username}
        self._rooms: dict[str, dict[WSLike, str]] = {}

    async def connect(self, room: str, websocket: WSLike, username: str) -> None:
        """Accept a connection and register it under ``room``."""
        await websocket.accept()
        self._rooms.setdefault(room, {})[websocket] = username

    def disconnect(self, room: str, websocket: WSLike) -> None:
        """Remove a connection; drop the room entry once it's empty."""
        connections = self._rooms.get(room)
        if connections and websocket in connections:
            del connections[websocket]
            if not connections:
                del self._rooms[room]

    def usernames(self, room: str) -> list[str]:
        """Distinct usernames currently connected to ``room``, sorted."""
        return sorted(set(self._rooms.get(room, {}).values()))

    def count(self, room: str) -> int:
        return len(self._rooms.get(room, {}))

    async def broadcast(self, room: str, payload: dict) -> None:
        """Send ``payload`` (as JSON) to every connection in ``room``.

        Connections that error out are skipped here; they get fully removed
        when their socket raises ``WebSocketDisconnect`` in the endpoint loop.
        """
        for websocket in list(self._rooms.get(room, {}).keys()):
            try:
                await websocket.send_json(payload)
            except Exception:
                pass

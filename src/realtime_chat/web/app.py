"""FastAPI app: a WebSocket chat endpoint, a REST history endpoint, and the UI.

Message flow for a connected client:
  1. on join  -> receive a ``history`` frame, then a ``presence`` frame
  2. others   -> receive a ``system`` "joined" frame and an updated ``presence``
  3. on send  -> everyone (incl. sender) receives a ``message`` frame
  4. on leave -> others receive ``system`` "left" and updated ``presence``
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .. import service
from ..config import get_settings
from ..db import get_engine, get_session, init_db
from ..manager import ConnectionManager

STATIC_DIR = Path(__file__).parent / "static"

manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="realtime-chat", description="WebSocket chat with rooms.", lifespan=lifespan)


def _clean_room(room: str) -> str:
    return room.strip().lower()[:50] or "lobby"


def _clean_username(name: str) -> str:
    return name.strip()[:32] or "anonymous"


def _presence_payload(room: str) -> dict:
    return {"type": "presence", "users": manager.usernames(room), "count": manager.count(room)}


@app.get("/api/rooms/{room}/messages")
def history(room: str, session: Session = Depends(get_session)) -> list[dict]:
    """Recent message history for a room (handy for clients/tests)."""
    limit = get_settings().history_limit
    return [service.message_payload(m) for m in service.recent_messages(session, _clean_room(room), limit)]


@app.websocket("/ws/{room}")
async def chat(websocket: WebSocket, room: str, username: str = Query("anonymous")) -> None:
    settings = get_settings()
    room = _clean_room(room)
    username = _clean_username(username)

    await manager.connect(room, websocket, username)
    try:
        # 1. Send this client the recent history.
        with Session(get_engine()) as session:
            recent = service.recent_messages(session, room, settings.history_limit)
        await websocket.send_json(
            {"type": "history", "messages": [service.message_payload(m) for m in recent]}
        )

        # 2. Announce the new arrival to everyone and refresh presence.
        await manager.broadcast(room, {"type": "system", "content": f"{username} joined"})
        await manager.broadcast(room, _presence_payload(room))

        # 3. Relay messages until the client disconnects.
        while True:
            data = await websocket.receive_json()
            content = str(data.get("content", "")).strip()[: settings.max_message_length]
            if not content:
                continue
            with Session(get_engine()) as session:
                message = service.save_message(session, room, username, content)
            await manager.broadcast(room, service.message_payload(message))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(room, websocket)
        await manager.broadcast(room, {"type": "system", "content": f"{username} left"})
        await manager.broadcast(room, _presence_payload(room))


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the web server (used by the ``chat-web`` entry point)."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()

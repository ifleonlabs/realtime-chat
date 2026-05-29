"""FastAPI app: auth, room management, an authenticated WebSocket, and the SPA.

All real-time traffic flows over ``/ws/{slug}`` (JWT passed as a query param);
everything else is a normal JSON REST API under ``/api``. The built React
frontend in ``frontend/dist`` is served at the root when present.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .. import messages, rooms, users
from ..cleanup import run_cleanup_loop
from ..config import get_settings
from ..db import get_engine, get_session, init_db
from ..deps import get_current_user, user_from_ws_token
from ..manager import ConnectionManager
from ..models import Room, User
from ..rooms import RoomError
from ..schemas import (
    JoinRequest,
    RoomCreate,
    RoomRead,
    Token,
    UserCreate,
    UserRead,
)  # noqa: F401
from ..security import create_access_token
from ..users import AuthError

log = logging.getLogger("realtime_chat")
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"

manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if get_settings().is_using_default_secret:
        log.warning("CHAT_JWT_SECRET is the insecure default; set it in production.")
    task = asyncio.create_task(run_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="realtime-chat", description="Authenticated WebSocket chat with rooms.", lifespan=lifespan)


# --- helpers ---------------------------------------------------------------
def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Treat naive datetimes (from SQLite) as UTC so clients get an offset."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _room_read(session: Session, room: Room, user: User) -> RoomRead:
    owner = users.get_by_id(session, room.owner_id)
    is_owner = room.owner_id == user.id
    return RoomRead(
        id=room.id,
        slug=room.slug,
        name=room.name,
        description=room.description,
        is_private=room.is_private,
        owner_username=owner.username if owner else "?",
        member_count=rooms.member_count(session, room.id),
        created_at=_aware(room.created_at),
        message_ttl_seconds=room.message_ttl_seconds,
        is_owner=is_owner,
        is_member=is_owner or rooms.is_member(session, user.id, room.id),
        join_code=room.join_code if (is_owner and room.is_private) else None,
    )


def _token_response(session: Session, user: User) -> Token:
    return Token(
        access_token=create_access_token(str(user.id)),
        user=UserRead(id=user.id, username=user.username, created_at=_aware(user.created_at)),
    )


# --- auth ------------------------------------------------------------------
@app.post("/api/auth/register", response_model=Token, status_code=201, tags=["auth"])
def register(data: UserCreate, session: Session = Depends(get_session)) -> Token:
    try:
        user = users.register(session, data)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _token_response(session, user)


@app.post("/api/auth/login", response_model=Token, tags=["auth"])
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> Token:
    try:
        user = users.authenticate(session, form.username, form.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return _token_response(session, user)


@app.get("/api/auth/me", response_model=UserRead, tags=["auth"])
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead(id=current_user.id, username=current_user.username, created_at=_aware(current_user.created_at))


# --- rooms -----------------------------------------------------------------
@app.post("/api/rooms", response_model=RoomRead, status_code=201, tags=["rooms"])
def create_room(
    data: RoomCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RoomRead:
    room = rooms.create(session, user, data)
    return _room_read(session, room, user)


@app.get("/api/rooms", response_model=list[RoomRead], tags=["rooms"])
def list_public_rooms(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[RoomRead]:
    return [_room_read(session, r, user) for r in rooms.list_public(session)]


@app.get("/api/rooms/mine", response_model=list[RoomRead], tags=["rooms"])
def list_my_rooms(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[RoomRead]:
    return [_room_read(session, r, user) for r in rooms.list_for_user(session, user)]


def _get_visible_room(session: Session, slug: str, user: User) -> Room:
    """Fetch a room the user is allowed to see, else 404 (hides private rooms)."""
    room = rooms.get_by_slug(session, slug)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    if room.is_private and not rooms.has_access(session, user, room):
        raise HTTPException(status_code=404, detail="Room not found.")
    return room


@app.get("/api/rooms/{slug}", response_model=RoomRead, tags=["rooms"])
def get_room(
    slug: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RoomRead:
    return _room_read(session, _get_visible_room(session, slug, user), user)


@app.post("/api/rooms/{slug}/join", response_model=RoomRead, tags=["rooms"])
def join_room(
    slug: str,
    body: JoinRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RoomRead:
    room = rooms.get_by_slug(session, slug)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    try:
        rooms.join(session, user, room, code=body.code)
    except RoomError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _room_read(session, room, user)


@app.delete("/api/rooms/{slug}", status_code=204, tags=["rooms"])
async def delete_room(
    slug: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    room = rooms.get_by_slug(session, slug)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    if room.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can delete this room.")
    rooms.delete_room(session, room)
    await manager.close_room(slug, {"type": "system", "content": "This room was closed by its owner."})


@app.get("/api/rooms/{slug}/messages", tags=["rooms"])
def room_history(
    slug: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    room = _get_visible_room(session, slug, user)
    if not rooms.has_access(session, user, room):
        raise HTTPException(status_code=403, detail="Join the room first.")
    limit = get_settings().history_limit
    return [messages.payload(m) for m in messages.recent(session, room.id, limit)]


# --- websocket -------------------------------------------------------------
def _presence(slug: str) -> dict:
    return {"type": "presence", "users": manager.usernames(slug), "count": manager.count(slug)}


@app.websocket("/ws/{slug}")
async def chat(websocket: WebSocket, slug: str, token: str = Query(None)) -> None:
    settings = get_settings()
    # Authenticate + authorize before accepting the socket.
    with Session(get_engine()) as session:
        user = user_from_ws_token(token, session)
        if user is None:
            await websocket.close(code=4401)  # unauthorized
            return
        room = rooms.get_by_slug(session, slug)
        if room is None:
            await websocket.close(code=4404)  # gone
            return
        if not rooms.has_access(session, user, room):
            await websocket.close(code=4403)  # forbidden
            return
        room_id = room.id
        ttl_seconds = room.message_ttl_seconds
        user_id = user.id
        username = user.username
        history = [messages.payload(m) for m in messages.recent(session, room_id, settings.history_limit)]

    await manager.connect(slug, websocket, username)
    try:
        await websocket.send_json({"type": "history", "messages": history})
        await manager.broadcast(slug, {"type": "system", "content": f"{username} joined"})
        await manager.broadcast(slug, _presence(slug))

        while True:
            data = await websocket.receive_json()
            content = str(data.get("content", "")).strip()[: settings.max_message_length]
            if not content:
                continue
            with Session(get_engine()) as session:
                message = messages.save(session, room_id, user_id, username, content, ttl_seconds)
            await manager.broadcast(slug, messages.payload(message))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(slug, websocket)
        await manager.broadcast(slug, {"type": "system", "content": f"{username} left"})
        await manager.broadcast(slug, _presence(slug))


# --- frontend (served last so it never shadows the API) --------------------
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
else:
    @app.get("/", include_in_schema=False)
    def _no_build() -> HTMLResponse:
        return HTMLResponse(
            "<h1>realtime-chat API</h1>"
            "<p>The React frontend isn't built yet. During development run "
            "<code>npm run dev</code> in <code>frontend/</code>, or build it with "
            "<code>npm run build</code> to have it served here.</p>"
            "<p>API docs: <a href='/docs'>/docs</a></p>"
        )


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the web server (used by the ``chat-web`` entry point)."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()

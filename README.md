# realtime-chat

A real-time chat server built on **WebSockets** with [FastAPI](https://fastapi.tiangolo.com/): multiple rooms, live presence ("who's online"), and message history persisted in SQLite via [SQLModel](https://sqlmodel.tiangolo.com/). Includes a browser frontend and a CLI. Managed with [uv](https://docs.astral.sh/uv/).

This is project #5 in a series of Python projects, progressing from basic to advanced.

## What this project demonstrates

- **WebSockets** in FastAPI (`@app.websocket`) — a persistent, bidirectional connection instead of request/response
- A **ConnectionManager** that tracks live connections per room and **broadcasts** to them
- **Presence**: clients are told who's online as people join and leave
- **Message history** persisted to a database and replayed when a client joins
- A real-time browser frontend using the native **WebSocket API**
- Tests covering the manager, persistence, and the **full WebSocket flow** (via Starlette's test client) — no real network needed

## Install & run

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/ifleonlabs/realtime-chat.git
cd realtime-chat
uv sync
uv run chat serve        # http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000> in **two browser tabs**, pick different names and
the same room, and watch messages appear instantly in both.

## How it works

A connected client exchanges JSON frames over the socket:

| `type` | Direction | Meaning |
|--------|-----------|---------|
| `history` | server → client | recent messages, sent right after joining |
| `presence` | server → client | the current list of online users |
| `system` | server → client | "X joined" / "X left" notices |
| `message` | both ways | a chat message (client sends `{ "content": "..." }`) |

WebSocket endpoint: `ws://HOST:PORT/ws/{room}?username=<name>`
REST history (handy for clients/tests): `GET /api/rooms/{room}/messages`

## CLI

```bash
chat serve                 # run the web UI + WebSocket server
chat rooms                 # list rooms with message counts
chat history general -n 20 # print recent messages for a room
```

## Configuration

Copy `.env.example` to `.env` (all optional):

| Variable | Default | Meaning |
|----------|---------|---------|
| `CHAT_DATABASE_URL` | `sqlite:///~/.realtime-chat/chat.db` | Any SQLAlchemy URL |
| `CHAT_HISTORY_LIMIT` | `50` | Messages sent to a client on join |
| `CHAT_MAX_MESSAGE_LENGTH` | `2000` | Max length of a single message |

## Development

```bash
uv sync                  # install runtime + dev dependencies
uv run pytest            # run the test suite (17 tests)
```

## Project layout

```
realtime-chat/
├── pyproject.toml           # metadata, deps, entry points
├── main.py                  # run the CLI without installing
├── .env.example             # copy to .env to configure
├── src/realtime_chat/
│   ├── config.py            # pydantic-settings (.env / env vars)
│   ├── db.py                # engine, session, init_db
│   ├── models.py            # SQLModel Message table
│   ├── manager.py           # ConnectionManager: rooms, broadcast, presence
│   ├── service.py           # message persistence + history
│   ├── cli.py               # Typer commands
│   └── web/
│       ├── app.py           # FastAPI: WebSocket endpoint + REST history
│       └── static/          # chat frontend (index.html, style.css, app.js)
└── tests/                   # manager, service, and WebSocket-flow tests
```

## License

MIT

# realtime-chat

A full-stack real-time chat app: **accounts**, **user-created rooms** (public or private), **ephemeral rolling messages**, and live **WebSocket** messaging with presence. Built with a **FastAPI** backend ([SQLModel](https://sqlmodel.tiangolo.com/) + JWT auth) and a **React + TypeScript** frontend ([Vite](https://vitejs.dev/)).

This is project #5 in a series of Python projects. **v0.3.0** makes messages ephemeral: the room stays open and each message rolls off on its own timer.

## Features

- **Accounts** — register / log in; passwords hashed with bcrypt, sessions via JWT
- **Rooms you create** — give them a name + description
- **Public or private** — public rooms are listed for everyone; private rooms are hidden and require a **join code**
- **Ephemeral rolling messages** — each message lives for the room's chosen lifetime (presets up to **24 hours**, or a **custom** time; 24h is the hard maximum) and then disappears **one by one**, oldest first. The room itself keeps running. A background task deletes expired messages; the UI hides them the moment they expire.
- **Live timer at the top** of each room counts down to when the next (oldest) message will vanish.
- **Real-time** — instant messaging over WebSockets, with **live presence** (who's online) and recent (non-expired) **history** replayed on join
- **A polished React UI** plus a Typer CLI for administration

## What this version demonstrates

- Combining **authentication** (JWT) with **WebSockets** — the socket is authorized via a token before it's accepted
- **Authorization / data ownership** — room membership and owner-only actions
- A **background task** (in the app lifespan) for scheduled cleanup
- A real **frontend/backend split**: a Vite React SPA talking to a FastAPI JSON + WebSocket API
- A backend test suite (32 tests) covering auth, rooms, access control, expiry, and the full WebSocket flow

## Run it

Requires [uv](https://docs.astral.sh/uv/) (backend) and [Node.js](https://nodejs.org/) (frontend).

### Development (two terminals, hot-reload frontend)

```bash
# Terminal 1 — backend API + WebSocket on :8000
uv sync
uv run chat serve

# Terminal 2 — React dev server on :5173 (proxies /api and /ws to :8000)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>, sign up, and create a room. Open a second browser
(or an incognito window) as another user to chat in real time.

### Production-style (one server)

Build the frontend once; the backend then serves it at `/`:

```bash
cd frontend && npm install && npm run build && cd ..
uv run chat serve          # http://127.0.0.1:8000 serves the built app + API
```

> Set `CHAT_JWT_SECRET` to a long random value (see `.env.example`) for anything
> beyond local use. The server warns on startup if the insecure default is used.

## API overview

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth/register` | create an account → returns a token |
| `POST` | `/api/auth/login` | log in (OAuth2 form) → returns a token |
| `GET`  | `/api/auth/me` | the current user |
| `GET`  | `/api/rooms` | list public rooms |
| `GET`  | `/api/rooms/mine` | rooms you own or have joined |
| `POST` | `/api/rooms` | create a room (name, private?, lifetime) |
| `POST` | `/api/rooms/{slug}/join` | join (with a code for private rooms) |
| `DELETE` | `/api/rooms/{slug}` | delete a room (owner only) |
| `WS`   | `/ws/{slug}?token=…` | the real-time channel (JWT required) |

Interactive API docs: <http://127.0.0.1:8000/docs>.

## CLI (admin)

```bash
chat serve            # run the server
chat users            # list registered users
chat rooms            # list rooms (visibility, members, message lifetime)
chat purge            # delete expired messages now
```

## Project layout

```
realtime-chat/
├── pyproject.toml
├── main.py                       # run the CLI without installing
├── .env.example
├── src/realtime_chat/            # FastAPI backend
│   ├── config.py  db.py  models.py
│   ├── security.py               # bcrypt + JWT
│   ├── users.py  rooms.py  messages.py   # service layer
│   ├── deps.py                   # auth dependencies (HTTP + WebSocket)
│   ├── manager.py                # in-memory connection/broadcast layer
│   ├── cleanup.py                # background task: delete expired messages
│   ├── cli.py
│   └── web/app.py                # API + WebSocket + serves the built SPA
├── frontend/                     # Vite + React + TypeScript
│   ├── src/api.ts  auth.tsx  App.tsx
│   └── src/pages/ Login · Rooms · Chat
└── tests/                        # services, API, WebSocket, manager
```

## Development

```bash
uv run pytest                 # backend tests (36)
cd frontend && npm run build  # verify the frontend compiles
```

## License

MIT

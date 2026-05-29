import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, tokenStore } from "../api";
import { useAuth } from "../auth";
import type { ChatMessage, Frame, Room } from "../types";

type FeedItem = { kind: "msg"; m: ChatMessage } | { kind: "sys"; text: string };

function formatRemaining(ms: number): string {
  if (ms <= 0) return "0s";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function ttlLabel(seconds: number): string {
  const mins = Math.round(seconds / 60);
  return mins % 60 === 0 ? `${mins / 60}h` : `${mins}m`;
}

export default function Chat() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [room, setRoom] = useState<Room | null>(null);
  const [phase, setPhase] = useState<"loading" | "needcode" | "ready" | "error">("loading");
  const [code, setCode] = useState("");
  const [errMsg, setErrMsg] = useState("");

  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [users, setUsers] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(Date.now());

  const wsRef = useRef<WebSocket | null>(null);
  const feedEndRef = useRef<HTMLDivElement | null>(null);

  // Resolve access to the room (auto-join public; prompt for private code).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPhase("loading");
      try {
        let r = await api.getRoom(slug);
        if (!r.is_member) r = await api.joinRoom(slug);
        if (!cancelled) { setRoom(r); setPhase("ready"); }
      } catch {
        if (!cancelled) setPhase("needcode");
      }
    })();
    return () => { cancelled = true; };
  }, [slug]);

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setErrMsg("");
    try {
      const r = await api.joinRoom(slug, code.trim());
      setRoom(r);
      setPhase("ready");
    } catch (err) {
      setErrMsg(err instanceof ApiError ? err.message : "Could not join this room.");
    }
  }

  // Open the WebSocket once we have access.
  useEffect(() => {
    if (phase !== "ready" || !room) return;
    const token = tokenStore.get();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/${room.slug}?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (ev) => {
      const frame: Frame = JSON.parse(ev.data);
      if (frame.type === "history") {
        setFeed(frame.messages.map((m) => ({ kind: "msg", m })));
      } else if (frame.type === "message") {
        setFeed((f) => [...f, { kind: "msg", m: frame }]);
      } else if (frame.type === "system") {
        setFeed((f) => [...f, { kind: "sys", text: frame.content }]);
      } else if (frame.type === "presence") {
        setUsers(frame.users);
      }
    };
    return () => ws.close();
  }, [phase, room?.slug]);

  // Every second: advance the clock AND drop messages that have rolled off,
  // so they visibly disappear one by one (oldest first).
  useEffect(() => {
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      setFeed((f) =>
        f.filter((item) => item.kind !== "msg" || new Date(item.m.expires_at).getTime() > t)
      );
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Auto-scroll on new messages.
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [feed]);

  function send(e: FormEvent) {
    e.preventDefault();
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem("msg") as HTMLInputElement;
    const content = input.value.trim();
    if (!content || wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ content }));
    input.value = "";
  }

  if (phase === "loading") return <div className="center muted">Joining room…</div>;

  if (phase === "needcode") {
    return (
      <div className="center">
        <form className="card auth-card" onSubmit={submitCode}>
          <h2>🔒 Private room</h2>
          <p className="muted">Enter the room's join code to continue.</p>
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="join code" autoFocus />
          {errMsg && <p className="error">{errMsg}</p>}
          <button className="primary" type="submit">Join</button>
          <button className="ghost" type="button" onClick={() => navigate("/")}>Back</button>
        </form>
      </div>
    );
  }

  // The next message to vanish is the oldest one still on screen.
  const oldest = feed.find((item) => item.kind === "msg") as { kind: "msg"; m: ChatMessage } | undefined;
  const nextExpiryMs = oldest ? new Date(oldest.m.expires_at).getTime() - now : null;

  return (
    <div className="chat-page">
      <header className="topbar">
        <button className="ghost" onClick={() => navigate("/")}>← Rooms</button>
        <span className="brand-sm">
          {room?.is_private ? "🔒 " : "# "}{room?.name}
        </span>
        <span className={connected ? "status live" : "status"}>{connected ? "live" : "connecting…"}</span>
        <span className="spacer" />
        {nextExpiryMs !== null ? (
          <span className={nextExpiryMs < 60_000 ? "pill danger" : "pill"} title="Time until the oldest message disappears">
            ⏳ next message in {formatRemaining(nextExpiryMs)}
          </span>
        ) : (
          room && <span className="pill" title="How long messages live in this room">⏳ messages last {ttlLabel(room.message_ttl_seconds)}</span>
        )}
      </header>

      {room?.join_code && (
        <div className="code-banner">
          Share this private room with code <code>{room.join_code}</code>
        </div>
      )}

      <div className="chat-body">
        <main className="messages">
          {feed.map((item, i) =>
            item.kind === "sys" ? (
              <div className="system" key={i}>{item.text}</div>
            ) : (
              <div className={"msg" + (item.m.username === user?.username ? " me" : "")} key={i}>
                <div className="who">
                  {item.m.username}
                  <span className="time">
                    {new Date(item.m.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                <div className="text">{item.m.content}</div>
              </div>
            )
          )}
          <div ref={feedEndRef} />
        </main>

        <aside className="presence">
          <h3>Online · {users.length}</h3>
          <ul>
            {users.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </aside>
      </div>

      <form className="message-form" onSubmit={send}>
        <input name="msg" placeholder="Type a message…" autoComplete="off" autoFocus />
        <button className="primary" type="submit">Send</button>
      </form>
    </div>
  );
}

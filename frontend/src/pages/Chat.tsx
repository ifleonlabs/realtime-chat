import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, tokenStore } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../components/Icon";
import type { ChatMessage, Frame, Room } from "../types";

type FeedItem = { kind: "msg"; m: ChatMessage } | { kind: "sys"; text: string };

const AVATAR_COLORS = ["#5b7cfa", "#7c5cf0", "#2dd4a7", "#f59e0b", "#ec4899", "#06b6d4", "#8b5cf6", "#ef4444"];
function avatarColor(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}
const initials = (name: string) => name.slice(0, 2).toUpperCase();

function formatRemaining(ms: number): string {
  if (ms <= 0) return "0s";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
const ttlLabel = (seconds: number) => {
  const mins = Math.round(seconds / 60);
  return mins % 60 === 0 ? `${mins / 60}h` : `${mins}m`;
};
const timeOf = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yest = new Date(); yest.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "Today";
  if (same(d, yest)) return "Yesterday";
  return d.toLocaleDateString(undefined, { month: "long", day: "numeric" });
}

// Render rows: insert date dividers and mark consecutive messages from the
// same author (within 5 min) as "grouped" so the avatar/name show only once.
type Row =
  | { kind: "divider"; label: string }
  | { kind: "sys"; text: string }
  | { kind: "msg"; m: ChatMessage; grouped: boolean };

function buildRows(feed: FeedItem[]): Row[] {
  const out: Row[] = [];
  let lastDay: string | null = null;
  let prev: { user: string; t: number } | null = null;
  for (const item of feed) {
    if (item.kind === "sys") {
      out.push({ kind: "sys", text: item.text });
      prev = null;
      continue;
    }
    const day = dayLabel(item.m.created_at);
    if (day !== lastDay) {
      out.push({ kind: "divider", label: day });
      lastDay = day;
      prev = null;
    }
    const t = new Date(item.m.created_at).getTime();
    const grouped = !!prev && prev.user === item.m.username && t - prev.t < 5 * 60 * 1000;
    out.push({ kind: "msg", m: item.m, grouped });
    prev = { user: item.m.username, t };
  }
  return out;
}

export default function Chat() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [room, setRoom] = useState<Room | null>(null);
  const [phase, setPhase] = useState<"loading" | "needcode" | "ready">("loading");
  const [code, setCode] = useState("");
  const [errMsg, setErrMsg] = useState("");

  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [users, setUsers] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(Date.now());

  const wsRef = useRef<WebSocket | null>(null);
  const feedEndRef = useRef<HTMLDivElement | null>(null);

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
      if (frame.type === "history") setFeed(frame.messages.map((m) => ({ kind: "msg", m })));
      else if (frame.type === "message") setFeed((f) => [...f, { kind: "msg", m: frame }]);
      else if (frame.type === "system") setFeed((f) => [...f, { kind: "sys", text: frame.content }]);
      else if (frame.type === "presence") setUsers(frame.users);
    };
    return () => ws.close();
  }, [phase, room?.slug]);

  // Tick: advance clock and drop messages that have rolled off (oldest first).
  useEffect(() => {
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      setFeed((f) => f.filter((it) => it.kind !== "msg" || new Date(it.m.expires_at).getTime() > t));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => { feedEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [feed]);

  function send(e: FormEvent) {
    e.preventDefault();
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem("msg") as HTMLInputElement;
    const content = input.value.trim();
    if (!content || wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ content }));
    input.value = "";
  }

  if (phase === "loading")
    return <div className="center muted"><Icon name="clock" /> &nbsp;Joining room…</div>;

  if (phase === "needcode")
    return (
      <div className="center">
        <form className="card auth-card" onSubmit={submitCode}>
          <div className="auth-head"><span className="logo"><Icon name="lock" size={20} /></span></div>
          <h2 style={{ textAlign: "center", margin: 0 }}>Private room</h2>
          <p className="subtitle">Enter the room's join code to continue.</p>
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="join code" autoFocus />
          {errMsg && <p className="error">{errMsg}</p>}
          <button className="primary" type="submit">Join room</button>
          <button className="ghost" type="button" onClick={() => navigate("/")}>Back to rooms</button>
        </form>
      </div>
    );

  const rows = buildRows(feed);
  const oldest = feed.find((it) => it.kind === "msg") as { kind: "msg"; m: ChatMessage } | undefined;
  const nextExpiryMs = oldest ? new Date(oldest.m.expires_at).getTime() - now : null;

  return (
    <div className="chat-page">
      <header className="chat-header">
        <button className="ghost icon-only" title="Back to rooms" onClick={() => navigate("/")}><Icon name="back" /></button>
        <span className="room-icon" style={{ width: 34, height: 34, borderRadius: 10 }}>
          <Icon name={room?.is_private ? "lock" : "hash"} size={16} />
        </span>
        <div style={{ minWidth: 0 }}>
          <div className="brand-sm" style={{ fontSize: "1rem" }}>{room?.name}</div>
          <span className={connected ? "status live" : "status"}>{connected ? "live" : "connecting…"}</span>
        </div>
        <span className="spacer" />
        {nextExpiryMs !== null ? (
          <span className={nextExpiryMs < 60_000 ? "pill danger" : "pill"} title="Time until the oldest message disappears">
            <Icon name="clock" size={14} /> next in {formatRemaining(nextExpiryMs)}
          </span>
        ) : (
          room && <span className="pill" title="How long messages live here"><Icon name="clock" size={14} /> {ttlLabel(room.message_ttl_seconds)} lifetime</span>
        )}
      </header>

      {room?.join_code && (
        <div className="code-banner">🔑 Share this private room with code <code>{room.join_code}</code></div>
      )}

      <div className="chat-body">
        <main className="messages">
          {feed.length === 0 && (
            <p className="empty-hint">No messages yet — say hello! Messages here disappear after {room ? ttlLabel(room.message_ttl_seconds) : ""}.</p>
          )}
          {rows.map((row, i) => {
            if (row.kind === "divider") return <div className="date-divider" key={i}>{row.label}</div>;
            if (row.kind === "sys") return <div className="system" key={i}>{row.text}</div>;
            const mine = row.m.username === user?.username;
            return (
              <div className={`msg-row ${mine ? "me" : ""} ${row.grouped ? "grouped" : "start"}`} key={i}>
                {row.grouped ? (
                  <div className="avatar placeholder" />
                ) : (
                  <div className="avatar" style={{ background: avatarColor(row.m.username) }}>{initials(row.m.username)}</div>
                )}
                <div className="bubble-wrap">
                  {!row.grouped && (
                    <div className="who">{row.m.username}<span className="time">{timeOf(row.m.created_at)}</span></div>
                  )}
                  <div className="bubble">{row.m.content}</div>
                </div>
              </div>
            );
          })}
          <div ref={feedEndRef} />
        </main>

        <aside className="presence">
          <h3>Online · {users.length}</h3>
          <ul>
            {users.map((u) => (
              <li key={u}>
                <span className="avatar" style={{ width: 26, height: 26, fontSize: "0.62rem", background: avatarColor(u) }}>{initials(u)}</span>
                {u}
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <form className="composer" onSubmit={send}>
        <div className="composer-inner">
          <input name="msg" placeholder="Type a message…" autoComplete="off" autoFocus aria-label="Message" />
          <button className="primary send-btn" type="submit" aria-label="Send"><Icon name="send" size={18} /></button>
        </div>
      </form>
    </div>
  );
}

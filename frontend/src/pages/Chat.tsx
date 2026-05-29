import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, tokenStore } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../components/Icon";
import { PeerMesh, type MediaMeta } from "../webrtc";
import type { ChatMessage, Frame, Room } from "../types";

type FeedItem = { kind: "msg"; m: ChatMessage } | { kind: "sys"; text: string };

const MAX_FILE_BYTES = 25 * 1024 * 1024; // 25 MB cap for P2P transfer

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
function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Media messages are ordinary chat messages whose content is a JSON envelope.
function parseMedia(content: string): MediaMeta | null {
  if (!content.startsWith("{")) return null;
  try {
    const o = JSON.parse(content);
    return o && o._media ? (o._media as MediaMeta) : null;
  } catch {
    return null;
  }
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yest = new Date(); yest.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "Today";
  if (same(d, yest)) return "Yesterday";
  return d.toLocaleDateString(undefined, { month: "long", day: "numeric" });
}

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
    if (day !== lastDay) { out.push({ kind: "divider", label: day }); lastDay = day; prev = null; }
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
  const [typing, setTyping] = useState<Record<string, number>>({});
  const [mediaUrls, setMediaUrls] = useState<Record<string, string>>({}); // id -> object URL
  const [missing, setMissing] = useState<Record<string, boolean>>({}); // id -> unavailable

  const wsRef = useRef<WebSocket | null>(null);
  const meshRef = useRef<PeerMesh | null>(null);
  const feedEndRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const lastTypingRef = useRef(0);
  const requestedRef = useRef<Set<string>>(new Set());

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
      setRoom(r); setPhase("ready");
    } catch (err) {
      setErrMsg(err instanceof ApiError ? err.message : "Could not join this room.");
    }
  }

  // WebSocket + WebRTC peer mesh.
  useEffect(() => {
    if (phase !== "ready" || !room || !user) return;
    const token = tokenStore.get();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/${room.slug}?token=${token}`);
    wsRef.current = ws;

    const mesh = new PeerMesh(
      user.username,
      (target, signal) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "rtc", target, signal })); },
      (id, blob) => {
        const url = URL.createObjectURL(blob);
        setMediaUrls((m) => (m[id] ? (URL.revokeObjectURL(url), m) : { ...m, [id]: url }));
      },
    );
    meshRef.current = mesh;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (ev) => {
      const frame: Frame = JSON.parse(ev.data);
      if (frame.type === "history") setFeed(frame.messages.map((m) => ({ kind: "msg", m })));
      else if (frame.type === "message") {
        setFeed((f) => [...f, { kind: "msg", m: frame }]);
        setTyping((t) => { const { [frame.username]: _d, ...rest } = t; return rest; });
      } else if (frame.type === "system") setFeed((f) => [...f, { kind: "sys", text: frame.content }]);
      else if (frame.type === "presence") { setUsers(frame.users); mesh.setPeers(frame.users); }
      else if (frame.type === "typing") setTyping((t) => ({ ...t, [frame.username]: Date.now() + 4000 }));
      else if (frame.type === "rtc") void mesh.handleSignal(frame.from, frame.signal);
    };
    return () => { ws.close(); mesh.close(); meshRef.current = null; };
  }, [phase, room?.slug, user?.username]);

  // Tick: clock, message expiry, typing expiry.
  useEffect(() => {
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      setFeed((f) => f.filter((it) => it.kind !== "msg" || new Date(it.m.expires_at).getTime() > t));
      setTyping((tm) => {
        const next: Record<string, number> = {}; let changed = false;
        for (const [u, exp] of Object.entries(tm)) { if (exp > t) next[u] = exp; else changed = true; }
        return changed ? next : tm;
      });
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Request media blobs we don't have yet from peers; mark unavailable if none answer.
  useEffect(() => {
    for (const it of feed) {
      if (it.kind !== "msg") continue;
      const meta = parseMedia(it.m.content);
      if (!meta || mediaUrls[meta.id] || requestedRef.current.has(meta.id)) continue;
      requestedRef.current.add(meta.id);
      meshRef.current?.request(meta.id);
      const mid = meta.id;
      setTimeout(() => { if (!meshRef.current?.has(mid)) setMissing((u) => ({ ...u, [mid]: true })); }, 9000);
    }
  }, [feed, mediaUrls]);

  // Revoke object URLs and drop blobs when their message has rolled off.
  useEffect(() => {
    const live = new Set<string>();
    for (const it of feed) {
      if (it.kind === "msg") { const m = parseMedia(it.m.content); if (m) live.add(m.id); }
    }
    setMediaUrls((m) => {
      let changed = false; const next = { ...m };
      for (const id of Object.keys(m)) {
        if (!live.has(id)) {
          URL.revokeObjectURL(m[id]); delete next[id];
          meshRef.current?.drop(id); requestedRef.current.delete(id); changed = true;
        }
      }
      return changed ? next : m;
    });
  }, [feed]);

  useEffect(() => { feedEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [feed]);

  function send(e: FormEvent) {
    e.preventDefault();
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem("msg") as HTMLInputElement;
    const content = input.value.trim();
    if (!content || wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "message", content }));
    input.value = "";
  }

  function onType() {
    const t = Date.now();
    if (wsRef.current?.readyState === WebSocket.OPEN && t - lastTypingRef.current > 1800) {
      lastTypingRef.current = t;
      wsRef.current.send(JSON.stringify({ type: "typing" }));
    }
  }

  // Share a file: cache it locally + in the mesh, render immediately, and send
  // a media message (metadata only). The bytes are pulled peer-to-peer.
  function onPickFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) { alert("File is too large — 25 MB max for peer-to-peer transfer."); return; }
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    const meta: MediaMeta = { id: crypto.randomUUID(), name: file.name, mime: file.type || "application/octet-stream", size: file.size };
    meshRef.current?.put(meta.id, file, meta);
    const url = URL.createObjectURL(file);
    setMediaUrls((m) => ({ ...m, [meta.id]: url }));
    wsRef.current.send(JSON.stringify({ type: "message", content: JSON.stringify({ _media: meta }) }));
  }

  function renderMedia(meta: MediaMeta) {
    const url = mediaUrls[meta.id];
    if (url) {
      if (meta.mime.startsWith("image/"))
        return <a href={url} target="_blank" rel="noopener"><img className="media-img" src={url} alt={meta.name} /></a>;
      if (meta.mime.startsWith("video/"))
        return <video className="media-video" src={url} controls preload="metadata" />;
      if (meta.mime.startsWith("audio/"))
        return (
          <div className="media-audio-wrap">
            <div className="media-name">{meta.name}</div>
            <audio className="media-audio" src={url} controls preload="metadata" />
          </div>
        );
      return (
        <a className="media-file" href={url} download={meta.name}>
          <Icon name="file" size={18} />
          <span className="media-name">{meta.name}</span>
          <span className="media-size">{fmtSize(meta.size)}</span>
          <Icon name="download" size={16} />
        </a>
      );
    }
    if (missing[meta.id])
      return <div className="media-missing"><Icon name="file" size={16} /> {meta.name} — no longer available (no online source)</div>;
    return <div className="media-loading"><span className="spinner" /> Receiving {meta.name}…</div>;
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

  const typingNames = Object.keys(typing).filter((u) => u !== user?.username && typing[u] > now);
  const typingText =
    typingNames.length === 1 ? `${typingNames[0]} is typing`
    : typingNames.length === 2 ? `${typingNames[0]} and ${typingNames[1]} are typing`
    : typingNames.length > 2 ? "Several people are typing" : "";

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
            const media = parseMedia(row.m.content);
            return (
              <div className={`msg-row ${mine ? "me" : ""} ${row.grouped ? "grouped" : "start"}`} key={i}>
                {row.grouped ? <div className="avatar placeholder" /> : <div className="avatar" style={{ background: avatarColor(row.m.username) }}>{initials(row.m.username)}</div>}
                <div className="bubble-wrap">
                  {!row.grouped && <div className="who">{row.m.username}<span className="time">{timeOf(row.m.created_at)}</span></div>}
                  <div className={"bubble" + (media ? " media" : "")}>{media ? renderMedia(media) : row.m.content}</div>
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

      <div className="typing-row">
        {typingText && <span className="typing-indicator">{typingText}<span className="dots"><i /><i /><i /></span></span>}
      </div>

      <form className="composer" onSubmit={send}>
        <div className="composer-inner">
          <input ref={fileRef} type="file" hidden onChange={onPickFile} accept="image/*,video/*,audio/*,application/pdf,.txt,.doc,.docx,.zip" />
          <button type="button" className="ghost icon-only" title="Share a file (peer-to-peer)" onClick={() => fileRef.current?.click()}>
            <Icon name="paperclip" size={18} />
          </button>
          <input name="msg" placeholder="Type a message…" autoComplete="off" autoFocus aria-label="Message" onChange={onType} />
          <button className="primary send-btn" type="submit" aria-label="Send"><Icon name="send" size={18} /></button>
        </div>
      </form>
    </div>
  );
}

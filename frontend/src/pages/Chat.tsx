import { useEffect, useRef, useState, type ChangeEvent, type ClipboardEvent, type DragEvent, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, tokenStore } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../components/Icon";
import { PeerMesh, type MediaMeta } from "../webrtc";
import type { ChatMessage, Frame, Room } from "../types";

type FeedItem = { kind: "msg"; m: ChatMessage } | { kind: "sys"; id: number; text: string };

const MAX_FILE_BYTES = 25 * 1024 * 1024;
const EMOJIS = ["👍", "❤️", "😂", "🎉", "😮", "😢"];

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

function parseMedia(content: string): MediaMeta | null {
  if (!content.startsWith("{")) return null;
  try {
    const o = JSON.parse(content);
    return o && o._media ? (o._media as MediaMeta) : null;
  } catch {
    return null;
  }
}
function genId(): string {
  // crypto.randomUUID is unavailable on non-secure origins (e.g. LAN IP over
  // http), so fall back to a random string there.
  try { return crypto.randomUUID(); } catch { return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`; }
}
function previewOf(m: ChatMessage): string {
  const media = parseMedia(m.content);
  return media ? `📎 ${media.name}` : m.content.slice(0, 80);
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
  const [mediaUrls, setMediaUrls] = useState<Record<string, string>>({});
  const [missing, setMissing] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState<Record<string, { received: number; total: number }>>({});

  const [reactingId, setReactingId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [replyTo, setReplyTo] = useState<{ id: number; username: string; excerpt: string } | null>(null);
  const [dragging, setDragging] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const meshRef = useRef<PeerMesh | null>(null);
  const feedEndRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const lastTypingRef = useRef(0);
  const requestedRef = useRef<Map<string, number>>(new Map()); // media id -> first-requested ms
  const feedRef = useRef<FeedItem[]>([]);
  const urlsRef = useRef<Record<string, string>>({});
  feedRef.current = feed;
  urlsRef.current = mediaUrls;

  // --- access resolution -------------------------------------------------
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

  // --- websocket + peer mesh --------------------------------------------
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
        setProgress((p) => { const { [id]: _d, ...rest } = p; return rest; });
      },
      (id, received, total) => setProgress((p) => ({ ...p, [id]: { received, total } })),
    );
    meshRef.current = mesh;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (ev) => {
      const frame: Frame = JSON.parse(ev.data);
      if (frame.type === "history") setFeed(frame.messages.map((m) => ({ kind: "msg" as const, m })));
      else if (frame.type === "message") {
        setFeed((f) => [...f, { kind: "msg", m: frame }]);
        setTyping((t) => { const { [frame.username]: _d, ...rest } = t; return rest; });
      } else if (frame.type === "system") setFeed((f) => [...f, { kind: "sys", id: -Date.now(), text: frame.content }]);
      else if (frame.type === "presence") { setUsers(frame.users); mesh.setPeers(frame.users); }
      else if (frame.type === "typing") setTyping((t) => ({ ...t, [frame.username]: Date.now() + 4000 }));
      else if (frame.type === "rtc") void mesh.handleSignal(frame.from, frame.signal);
      else if (frame.type === "reaction") setFeed((f) => f.map((it) => (it.kind === "msg" && it.m.id === frame.id ? { kind: "msg", m: { ...it.m, reactions: frame.reactions } } : it)));
      else if (frame.type === "edited") setFeed((f) => f.map((it) => (it.kind === "msg" && it.m.id === frame.id ? { kind: "msg", m: { ...it.m, content: frame.content, edited: true } } : it)));
      else if (frame.type === "deleted") setFeed((f) => f.filter((it) => !(it.kind === "msg" && it.m.id === frame.id)));
    };
    return () => { ws.close(); mesh.close(); meshRef.current = null; };
  }, [phase, room?.slug, user?.username]);

  // --- timers / cleanup --------------------------------------------------
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

  // Pull missing media from peers. We RETRY on an interval because a data
  // channel usually isn't open yet the instant a media message arrives — the
  // WebRTC handshake takes a moment. Each tick re-asks any open peer until we
  // have the blob, then gives up (marks "unavailable") after a timeout.
  useEffect(() => {
    const pending = requestedRef.current;
    const iv = setInterval(() => {
      const t = Date.now();
      const liveMedia = new Set<string>();
      for (const it of feedRef.current) {
        if (it.kind !== "msg") continue;
        const meta = parseMedia(it.m.content);
        if (!meta) continue;
        liveMedia.add(meta.id);
        if (urlsRef.current[meta.id] || meshRef.current?.has(meta.id)) continue;
        const first = pending.get(meta.id);
        if (first === undefined) { pending.set(meta.id, t); }
        else if (t - first > 20000) { setMissing((u) => (u[meta.id] ? u : { ...u, [meta.id]: true })); continue; }
        meshRef.current?.request(meta.id);
      }
      for (const id of [...pending.keys()]) if (!liveMedia.has(id)) pending.delete(id);
    }, 1500);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    const live = new Set<string>();
    for (const it of feed) if (it.kind === "msg") { const m = parseMedia(it.m.content); if (m) live.add(m.id); }
    setMediaUrls((m) => {
      let changed = false; const next = { ...m };
      for (const id of Object.keys(m)) {
        if (!live.has(id)) { URL.revokeObjectURL(m[id]); delete next[id]; meshRef.current?.drop(id); requestedRef.current.delete(id); changed = true; }
      }
      return changed ? next : m;
    });
  }, [feed]);

  useEffect(() => { feedEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [feed]);

  // --- actions -----------------------------------------------------------
  function wsSend(obj: Record<string, unknown>) {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(obj));
  }

  function send(e: FormEvent) {
    e.preventDefault();
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem("msg") as HTMLInputElement;
    const content = input.value.trim();
    if (!content) return;
    wsSend({ type: "message", content, reply_to: replyTo?.id });
    input.value = "";
    setReplyTo(null);
  }

  function onType() {
    const t = Date.now();
    if (wsRef.current?.readyState === WebSocket.OPEN && t - lastTypingRef.current > 1800) {
      lastTypingRef.current = t;
      wsRef.current.send(JSON.stringify({ type: "typing" }));
    }
  }

  function shareFile(file: File) {
    if (file.size > MAX_FILE_BYTES) { alert("File is too large — 25 MB max for peer-to-peer transfer."); return; }
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    const meta: MediaMeta = { id: genId(), name: file.name, mime: file.type || "application/octet-stream", size: file.size };
    meshRef.current?.put(meta.id, file, meta);
    setMediaUrls((m) => ({ ...m, [meta.id]: URL.createObjectURL(file) }));
    wsSend({ type: "message", content: JSON.stringify({ _media: meta }), reply_to: replyTo?.id });
    setReplyTo(null);
  }

  function onPickFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) shareFile(file);
  }
  function onDrop(e: DragEvent) {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) shareFile(file);
  }
  function onPaste(e: ClipboardEvent) {
    const file = Array.from(e.clipboardData.files)[0];
    if (file) { e.preventDefault(); shareFile(file); }
  }

  function react(id: number, emoji: string) { wsSend({ type: "react", id, emoji }); setReactingId(null); }
  function startEdit(m: ChatMessage) { setEditingId(m.id); setEditValue(m.content); }
  function saveEdit(id: number) {
    const v = editValue.trim();
    if (v) wsSend({ type: "edit", id, content: v });
    setEditingId(null);
  }
  function del(id: number) { if (confirm("Delete this message?")) wsSend({ type: "delete", id }); }

  function renderMedia(meta: MediaMeta) {
    const url = mediaUrls[meta.id];
    if (url) {
      if (meta.mime.startsWith("image/")) return <a href={url} target="_blank" rel="noopener"><img className="media-img" src={url} alt={meta.name} /></a>;
      if (meta.mime.startsWith("video/")) return <video className="media-video" src={url} controls preload="metadata" />;
      if (meta.mime.startsWith("audio/")) return <div className="media-audio-wrap"><div className="media-name">{meta.name}</div><audio className="media-audio" src={url} controls preload="metadata" /></div>;
      return <a className="media-file" href={url} download={meta.name}><Icon name="file" size={18} /><span className="media-name">{meta.name}</span><span className="media-size">{fmtSize(meta.size)}</span><Icon name="download" size={16} /></a>;
    }
    if (missing[meta.id]) return <div className="media-missing"><Icon name="file" size={16} /> {meta.name} — no longer available (no online source)</div>;
    const p = progress[meta.id];
    const pct = p && p.total ? Math.round((p.received / p.total) * 100) : 0;
    return (
      <div className="media-loading">
        <span className="spinner" /> Receiving {meta.name}… {p ? `${pct}%` : ""}
        {p ? <span className="progress-track"><span className="progress-bar" style={{ width: `${pct}%` }} /></span> : null}
      </div>
    );
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

  const oldest = feed.find((it) => it.kind === "msg") as { kind: "msg"; m: ChatMessage } | undefined;
  const nextExpiryMs = oldest ? new Date(oldest.m.expires_at).getTime() - now : null;
  const typingNames = Object.keys(typing).filter((u) => u !== user?.username && typing[u] > now);
  const typingText =
    typingNames.length === 1 ? `${typingNames[0]} is typing`
    : typingNames.length === 2 ? `${typingNames[0]} and ${typingNames[1]} are typing`
    : typingNames.length > 2 ? "Several people are typing" : "";

  let lastDay: string | null = null;
  let prevUser: string | null = null;

  return (
    <div className="chat-page">
      <header className="chat-header">
        <button className="ghost icon-only" title="Back to rooms" onClick={() => navigate("/")}><Icon name="back" /></button>
        <span className="room-icon" style={{ width: 34, height: 34, borderRadius: 10 }}><Icon name={room?.is_private ? "lock" : "hash"} size={16} /></span>
        <div style={{ minWidth: 0 }}>
          <div className="brand-sm" style={{ fontSize: "1rem" }}>{room?.name}</div>
          <span className={connected ? "status live" : "status"}>{connected ? "live" : "connecting…"}</span>
        </div>
        <span className="spacer" />
        {nextExpiryMs !== null ? (
          <span className={nextExpiryMs < 60_000 ? "pill danger" : "pill"} title="Time until the oldest message disappears"><Icon name="clock" size={14} /> next in {formatRemaining(nextExpiryMs)}</span>
        ) : (
          room && <span className="pill" title="How long messages live here"><Icon name="clock" size={14} /> {ttlLabel(room.message_ttl_seconds)} lifetime</span>
        )}
      </header>

      {room?.join_code && <div className="code-banner">🔑 Share this private room with code <code>{room.join_code}</code></div>}

      <div className="chat-body">
        <main
          className={"messages" + (dragging ? " dropping" : "")}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          {feed.length === 0 && <p className="empty-hint">No messages yet — say hello! Messages here disappear after {room ? ttlLabel(room.message_ttl_seconds) : ""}. Drag a file in to share it.</p>}
          {feed.map((it, i) => {
            if (it.kind === "sys") { prevUser = null; return <div className="system" key={`s${i}`}>{it.text}</div>; }
            const m = it.m;
            const mine = m.username === user?.username;
            const media = parseMedia(m.content);
            const day = dayLabel(m.created_at);
            const showDate = day !== lastDay;
            lastDay = day;
            const grouped = !showDate && prevUser === m.username;
            prevUser = m.username;
            const reactionEntries = Object.entries(m.reactions || {});

            return (
              <div key={m.id}>
                {showDate && <div className="date-divider">{day}</div>}
                <div className={`msg-row ${mine ? "me" : ""} ${grouped ? "grouped" : "start"}`}>
                  {grouped ? <div className="avatar placeholder" /> : <div className="avatar" style={{ background: avatarColor(m.username) }}>{initials(m.username)}</div>}
                  <div className="bubble-wrap">
                    {!grouped && <div className="who">{m.username}<span className="time">{timeOf(m.created_at)}{m.edited ? " · edited" : ""}</span></div>}

                    <div className="bubble-stack">
                      <div className={"bubble" + (media ? " media" : "")}>
                        {m.reply && <div className="reply-quote"><span className="reply-who">{m.reply.username}</span><span className="reply-text">{m.reply.excerpt}</span></div>}
                        {editingId === m.id ? (
                          <div className="edit-box">
                            <input autoFocus value={editValue} onChange={(e) => setEditValue(e.target.value)}
                              onKeyDown={(e) => { if (e.key === "Enter") saveEdit(m.id); if (e.key === "Escape") setEditingId(null); }} />
                            <button className="primary" type="button" onClick={() => saveEdit(m.id)}>Save</button>
                            <button className="ghost" type="button" onClick={() => setEditingId(null)}>Cancel</button>
                          </div>
                        ) : media ? renderMedia(media) : m.content}
                      </div>

                      <div className="msg-tools">
                        <button title="React" onClick={() => setReactingId(reactingId === m.id ? null : m.id)}>😊</button>
                        <button title="Reply" onClick={() => setReplyTo({ id: m.id, username: m.username, excerpt: previewOf(m) })}>↩</button>
                        {mine && !media && <button title="Edit" onClick={() => startEdit(m)}>✎</button>}
                        {mine && <button title="Delete" onClick={() => del(m.id)}>🗑</button>}
                        {reactingId === m.id && <div className="emoji-pop">{EMOJIS.map((e) => <button key={e} onClick={() => react(m.id, e)}>{e}</button>)}</div>}
                      </div>
                    </div>

                    {reactionEntries.length > 0 && (
                      <div className="reactions">
                        {reactionEntries.map(([emoji, names]) => (
                          <button key={emoji} className={"reaction" + (user && names.includes(user.username) ? " mine" : "")}
                            title={names.join(", ")} onClick={() => react(m.id, emoji)}>{emoji} {names.length}</button>
                        ))}
                      </div>
                    )}
                  </div>
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
              <li key={u}><span className="avatar" style={{ width: 26, height: 26, fontSize: "0.62rem", background: avatarColor(u) }}>{initials(u)}</span>{u}</li>
            ))}
          </ul>
        </aside>
      </div>

      <div className="typing-row">
        {typingText && <span className="typing-indicator">{typingText}<span className="dots"><i /><i /><i /></span></span>}
      </div>

      {replyTo && (
        <div className="reply-bar">
          <span className="reply-who">↩ {replyTo.username}</span>
          <div className="reply-bar-text">{replyTo.excerpt}</div>
          <button className="ghost icon-only" type="button" onClick={() => setReplyTo(null)} title="Cancel reply">✕</button>
        </div>
      )}

      <form className="composer" onSubmit={send}>
        <div className="composer-inner">
          <input ref={fileRef} type="file" hidden onChange={onPickFile} accept="image/*,video/*,audio/*,application/pdf,.txt,.doc,.docx,.zip" />
          <button type="button" className="ghost icon-only" title="Share a file (peer-to-peer)" onClick={() => fileRef.current?.click()}><Icon name="paperclip" size={18} /></button>
          <input name="msg" placeholder="Type a message…" autoComplete="off" autoFocus aria-label="Message" onChange={onType} onPaste={onPaste} />
          <button className="primary send-btn" type="submit" aria-label="Send"><Icon name="send" size={18} /></button>
        </div>
      </form>
    </div>
  );
}

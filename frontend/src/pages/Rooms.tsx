import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../components/Icon";
import type { Room } from "../types";

function ttlLabel(room: Room): string {
  const mins = Math.round(room.message_ttl_seconds / 60);
  if (mins % 60 === 0) return `messages last ${mins / 60}h`;
  return `messages last ${mins}m`;
}

// Preset message lifetimes (minutes). 24h is the hard maximum; "Custom" lets
// the user enter any value up to 24h.
const TTL_PRESETS = [
  { label: "1 hour", minutes: 60 },
  { label: "6 hours", minutes: 360 },
  { label: "12 hours", minutes: 720 },
  { label: "24 hours", minutes: 1440 },
];
const MAX_MINUTES = 1440;

export default function Rooms() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [publicRooms, setPublicRooms] = useState<Room[]>([]);
  const [myRooms, setMyRooms] = useState<Room[]>([]);
  const [error, setError] = useState<string | null>(null);

  // create-room form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [preset, setPreset] = useState<string>("1440"); // minutes, or "custom"
  const [customHours, setCustomHours] = useState("2");

  async function refresh() {
    try {
      const [pub, mine] = await Promise.all([api.listPublic(), api.listMine()]);
      setPublicRooms(pub);
      setMyRooms(mine);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load rooms.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function chosenTtlMinutes(): number {
    if (preset === "custom") {
      const hours = parseFloat(customHours) || 0;
      return Math.min(MAX_MINUTES, Math.max(1, Math.round(hours * 60)));
    }
    return parseInt(preset, 10);
  }

  async function createRoom(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const room = await api.createRoom({
        name: name.trim(),
        description: description.trim(),
        is_private: isPrivate,
        ttl_minutes: chosenTtlMinutes(),
      });
      setName("");
      setDescription("");
      navigate(`/room/${room.slug}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create room.");
    }
  }

  async function open(room: Room) {
    try {
      if (!room.is_member) await api.joinRoom(room.slug);
      navigate(`/room/${room.slug}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't join that room.");
    }
  }

  async function remove(room: Room) {
    if (!confirm(`Delete room "${room.name}"? This removes its messages too.`)) return;
    await api.deleteRoom(room.slug);
    refresh();
  }

  const myRoomSlugs = new Set(myRooms.map((r) => r.slug));
  const browseable = publicRooms.filter((r) => !myRoomSlugs.has(r.slug));

  return (
    <div className="page">
      <header className="topbar">
        <span className="brand-sm"><Icon name="message" size={22} /> realtime-chat</span>
        <span className="spacer" />
        <span className="muted">@{user?.username}</span>
        <button className="ghost" onClick={logout}><Icon name="logout" size={16} /> Log out</button>
      </header>

      <main className="rooms-layout">
        <section>
          <form className="card create-form" onSubmit={createRoom}>
            <h2>Create a room</h2>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Room name" required maxLength={60} />
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" maxLength={200} />

            <label className="field-label">Messages disappear after</label>
            <div className="form-row">
              <select value={preset} onChange={(e) => setPreset(e.target.value)}>
                {TTL_PRESETS.map((p) => (
                  <option key={p.minutes} value={String(p.minutes)}>{p.label}</option>
                ))}
                <option value="custom">Custom…</option>
              </select>
              {preset === "custom" && (
                <input
                  type="number" min={0.1} max={24} step={0.5}
                  value={customHours}
                  onChange={(e) => setCustomHours(e.target.value)}
                  placeholder="hours (max 24)"
                  title="Hours, up to 24"
                />
              )}
            </div>

            <label className="check">
              <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} />
              Private (join by code)
            </label>

            <button className="primary" type="submit"><Icon name="plus" size={16} /> Create &amp; open</button>
          </form>

          {error && <p className="error">{error}</p>}

          {myRooms.length > 0 && (
            <>
              <h3 className="section-title">Your rooms</h3>
              <div className="room-list">
                {myRooms.map((room) => (
                  <div className="card room" key={room.slug}>
                    <div className="room-main">
                      <div className="room-name">
                        <Icon name={room.is_private ? "lock" : "hash"} size={16} />{room.name}
                        {room.is_owner && <span className="tag">owner</span>}
                      </div>
                      <div className="room-meta">
                        {room.member_count} member{room.member_count === 1 ? "" : "s"} · {ttlLabel(room)}
                      </div>
                      {room.join_code && (
                        <div className="code">code: <code>{room.join_code}</code></div>
                      )}
                    </div>
                    <div className="room-actions">
                      <button className="primary" onClick={() => navigate(`/room/${room.slug}`)}>Open</button>
                      {room.is_owner && <button className="ghost danger icon-only" title="Delete room" onClick={() => remove(room)}><Icon name="trash" size={16} /></button>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        <section>
          <h3 className="section-title">Public rooms</h3>
          {browseable.length === 0 ? (
            <p className="muted">No public rooms to join right now. Create one!</p>
          ) : (
            <div className="room-list">
              {browseable.map((room) => (
                <div className="card room" key={room.slug}>
                  <div className="room-main">
                    <div className="room-name"><Icon name="hash" size={16} />{room.name}</div>
                    {room.description && <div className="room-desc">{room.description}</div>}
                    <div className="room-meta">
                      by @{room.owner_username} · {room.member_count} member{room.member_count === 1 ? "" : "s"} · {ttlLabel(room)}
                    </div>
                  </div>
                  <div className="room-actions">
                    <button className="primary" onClick={() => open(room)}>Join</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

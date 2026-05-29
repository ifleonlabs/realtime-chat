import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import type { Lifetime, Room } from "../types";

function expiryLabel(room: Room): string {
  if (!room.expires_at) return "never expires";
  const ms = new Date(room.expires_at).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 24) return `expires in ${Math.floor(hours / 24)}d`;
  if (hours >= 1) return `expires in ${hours}h`;
  return `expires in ${Math.max(1, Math.floor(ms / 60_000))}m`;
}

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
  const [lifetime, setLifetime] = useState<Lifetime>("24h");

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

  async function createRoom(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const room = await api.createRoom({ name: name.trim(), description: description.trim(), is_private: isPrivate, lifetime });
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
        <span className="brand-sm">💬 realtime-chat</span>
        <span className="spacer" />
        <span className="muted">@{user?.username}</span>
        <button className="ghost" onClick={logout}>Log out</button>
      </header>

      <main className="rooms-layout">
        <section>
          <form className="card create-form" onSubmit={createRoom}>
            <h2>Create a room</h2>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Room name" required maxLength={60} />
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" maxLength={200} />
            <div className="form-row">
              <label className="check">
                <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} />
                Private (join by code)
              </label>
              <select value={lifetime} onChange={(e) => setLifetime(e.target.value as Lifetime)}>
                <option value="1h">Expires in 1 hour</option>
                <option value="24h">Expires in 24 hours</option>
                <option value="7d">Expires in 7 days</option>
                <option value="never">Never expires</option>
              </select>
            </div>
            <button className="primary" type="submit">Create &amp; open</button>
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
                        {room.is_private ? "🔒 " : "# "}{room.name}
                        {room.is_owner && <span className="tag">owner</span>}
                      </div>
                      <div className="room-meta">
                        {room.member_count} member{room.member_count === 1 ? "" : "s"} · {expiryLabel(room)}
                      </div>
                      {room.join_code && (
                        <div className="code">code: <code>{room.join_code}</code></div>
                      )}
                    </div>
                    <div className="room-actions">
                      <button className="primary" onClick={() => navigate(`/room/${room.slug}`)}>Open</button>
                      {room.is_owner && <button className="ghost danger" onClick={() => remove(room)}>Delete</button>}
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
                    <div className="room-name"># {room.name}</div>
                    {room.description && <div className="room-desc">{room.description}</div>}
                    <div className="room-meta">
                      by @{room.owner_username} · {room.member_count} member{room.member_count === 1 ? "" : "s"} · {expiryLabel(room)}
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

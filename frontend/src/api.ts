import type {
  AuthResponse,
  ChatMessage,
  CreateRoomInput,
  Room,
  User,
} from "./types";

const TOKEN_KEY = "chat_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(path, { ...options, headers });
  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.detail || `Request failed (${res.status})`);
  }
  return data as T;
}

function json(body: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const api = {
  // auth
  register: (username: string, password: string) =>
    request<AuthResponse>("/api/auth/register", json({ username, password })),

  login: (username: string, password: string) => {
    const body = new URLSearchParams({ username, password });
    return request<AuthResponse>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  },

  me: () => request<User>("/api/auth/me"),

  // rooms
  listPublic: () => request<Room[]>("/api/rooms"),
  listMine: () => request<Room[]>("/api/rooms/mine"),
  getRoom: (slug: string) => request<Room>(`/api/rooms/${slug}`),
  createRoom: (input: CreateRoomInput) => request<Room>("/api/rooms", json(input)),
  joinRoom: (slug: string, code = "") =>
    request<Room>(`/api/rooms/${slug}/join`, json({ code })),
  deleteRoom: (slug: string) => request<void>(`/api/rooms/${slug}`, { method: "DELETE" }),
  history: (slug: string) => request<ChatMessage[]>(`/api/rooms/${slug}/messages`),
};

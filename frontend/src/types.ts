export interface User {
  id: number;
  username: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Room {
  id: number;
  slug: string;
  name: string;
  description: string;
  is_private: boolean;
  owner_username: string;
  member_count: number;
  created_at: string;
  expires_at: string | null;
  is_owner: boolean;
  is_member: boolean;
  join_code: string | null;
}

export type Lifetime = "1h" | "24h" | "7d" | "never";

export interface CreateRoomInput {
  name: string;
  description?: string;
  is_private: boolean;
  lifetime: Lifetime;
}

export interface ChatMessage {
  type: "message";
  username: string;
  content: string;
  created_at: string;
}

export type Frame =
  | { type: "history"; messages: ChatMessage[] }
  | { type: "message"; username: string; content: string; created_at: string }
  | { type: "system"; content: string }
  | { type: "presence"; users: string[]; count: number };

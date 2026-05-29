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
  message_ttl_seconds: number;
  is_owner: boolean;
  is_member: boolean;
  join_code: string | null;
}

export interface CreateRoomInput {
  name: string;
  description?: string;
  is_private: boolean;
  ttl_minutes: number;
}

export interface ReplyInfo {
  username: string;
  excerpt: string;
}

export interface ChatMessage {
  type: "message";
  id: number;
  username: string;
  content: string;
  created_at: string;
  expires_at: string;
  edited: boolean;
  reactions: Record<string, string[]>; // emoji -> usernames
  reply: ReplyInfo | null;
}

export type Frame =
  | { type: "history"; messages: ChatMessage[] }
  | ChatMessage
  | { type: "system"; content: string }
  | { type: "presence"; users: string[]; count: number }
  | { type: "typing"; username: string }
  | { type: "rtc"; from: string; signal: unknown }
  | { type: "reaction"; id: number; reactions: Record<string, string[]> }
  | { type: "edited"; id: number; content: string }
  | { type: "deleted"; id: number };

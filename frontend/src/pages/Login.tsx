import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { ApiError } from "../api";
import { Icon } from "../components/Icon";

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(username.trim(), password);
      else await register(username.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <form className="card auth-card" onSubmit={submit}>
        <h1 className="brand"><Icon name="message" size={26} /> realtime-chat</h1>
        <p className="subtitle">Sign in to create rooms and chat in real time</p>
        <div className="tabs">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Log in
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Sign up
          </button>
        </div>

        <label>Username</label>
        <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required
               placeholder="3-32 letters, numbers, _" />

        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
               placeholder={mode === "register" ? "at least 6 characters" : "••••••••"} />

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={busy} className="primary">
          {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
    </div>
  );
}

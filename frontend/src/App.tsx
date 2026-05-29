import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import type { ReactNode } from "react";
import Login from "./pages/Login";
import Rooms from "./pages/Rooms";
import Chat from "./pages/Chat";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const { loading, user } = useAuth();
  if (loading) return <div className="center muted">Loading…</div>;

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/" element={<Protected><Rooms /></Protected>} />
      <Route path="/room/:slug" element={<Protected><Chat /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

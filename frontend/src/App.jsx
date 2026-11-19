import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { api, auth } from "./api";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Apply from "./pages/Apply.jsx";
import Profile from "./pages/Profile.jsx";
import Knowledge from "./pages/Knowledge.jsx";
import History from "./pages/History.jsx";
import Settings from "./pages/Settings.jsx";

function Shell() {
  const nav = useNavigate();
  const [user, setUser] = useState(null);
  useEffect(() => { api.get("/auth/me").then(setUser).catch(() => {}); }, []);
  const out = () => { auth.clear(); nav("/login"); };
  return (
    <div className="shell">
      <aside>
        <div className="brand">ApplyAI</div>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/apply">Apply</NavLink>
          <NavLink to="/profile">Profile</NavLink>
          <NavLink to="/knowledge">Saved answers</NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="who"><span>{user?.name}</span><button className="link" onClick={out}>Sign out</button></div>
      </aside>
      <main><Outlet /></main>
    </div>
  );
}

const Guard = () => (auth.get() ? <Shell /> : <Navigate to="/login" replace />);

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Guard />}>
        <Route index element={<Dashboard />} />
        <Route path="apply" element={<Apply />} />
        <Route path="apply/:id" element={<Apply />} />
        <Route path="profile" element={<Profile />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="history" element={<History />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

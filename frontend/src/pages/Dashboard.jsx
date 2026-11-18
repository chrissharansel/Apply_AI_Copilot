import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { StatusChip, host, when } from "../ui.jsx";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [apps, setApps] = useState([]);
  const [profile, setProfile] = useState(null);
  const [health, setHealth] = useState(null);
  useEffect(() => {
    api.get("/applications/stats").then(setStats).catch(() => {});
    api.get("/applications").then(setApps).catch(() => {});
    api.get("/profile").then(setProfile).catch(() => {});
    api.get("/agent/health").then(setHealth).catch(() => {});
  }, []);
  const figs = stats && [["Total", stats.total], ["Submitted", stats.submitted], ["In progress", stats.in_progress], ["Waiting for you", stats.waiting], ["Needs attention", stats.failed]];
  return (
    <div className="page">
      <h1>Dashboard</h1>
      {profile && !profile.confirmed && <p className="notice warn">Your profile isn’t confirmed yet. The agent only uses confirmed details. <Link to="/profile">Review your profile</Link></p>}
      {health && !health.ok && <p className="notice bad">GitHub Copilot CLI isn’t available: {health.error} Then sign in once by running <code>copilot</code> and typing <code>/login</code>.</p>}
      {figs && <div className="figs">{figs.map(([l, n]) => <div key={l}><b>{n}</b><span>{l}</span></div>)}</div>}
      <div className="row between"><h2>Recent applications</h2><Link className="btn primary" to="/apply">New application</Link></div>
      {apps.length === 0 ? <p className="muted">Nothing yet. Paste a job link on the Apply page to start.</p> : (
        <table><thead><tr><th>Role</th><th>Company</th><th>Site</th><th>Status</th><th>Started</th></tr></thead><tbody>
          {apps.slice(0, 8).map((a) => (
            <tr key={a.id}><td><Link to={`/apply/${a.session_id}`}>{a.job_title || "Untitled role"}</Link></td><td>{a.company}</td><td>{host(a.url)}</td><td><StatusChip status={a.status} /></td><td>{when(a.created_at)}</td></tr>
          ))}
        </tbody></table>
      )}
    </div>
  );
}

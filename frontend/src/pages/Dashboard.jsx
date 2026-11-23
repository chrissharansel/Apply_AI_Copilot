import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { StatusChip, host, when, Chip } from "../ui.jsx";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [apps, setApps] = useState([]);
  const [profile, setProfile] = useState(null);
  const [health, setHealth] = useState(null);
  const [nConf, setNConf] = useState(0);

  useEffect(() => {
    api.get("/applications/stats").then(setStats).catch(() => {});
    api.get("/applications").then(setApps).catch(() => {});
    api.get("/profile").then(setProfile).catch(() => {});
    api.get("/agent/health").then(setHealth).catch(() => {});
    api.get("/profile/conflicts").then((c) => setNConf(c.conflicts.filter((x) => x.kind !== "missing_in_resume").length)).catch(() => {});
  }, []);

  const metrics = stats && [
    ["Applications", stats.total, "All tracked job applications"],
    ["Submitted", stats.submitted, "Successfully submitted"],
    ["In progress", stats.in_progress, "Active agent sessions"],
    ["Your attention", stats.waiting + stats.failed, "Questions or issues to resolve"],
  ];

  return (
    <div className="page dashboard-page">
      <section className="dashboard-hero">
        <div><div className="eyebrow">APPLICANT WORKSPACE</div><h1>Your job search command center</h1>
          <p className="muted">Prepare each application with the right resume, confirmed candidate facts and a reviewable AI-assisted workflow.</p>
          <div className="row wrap"><Link className="btn primary" to="/apply">Start an application</Link><Link className="btn" to="/profile">Manage profile & resumes</Link></div>
        </div>
        <div className="hero-status">
          <Chip cls={health?.ok ? "c-green" : "c-amber"}>{health?.ok ? "AI engine detected" : "AI engine needs attention"}</Chip>
          <span className="muted small">{health?.model || "Checking AI engine…"}</span>
        </div>
      </section>

      {profile && !profile.confirmed && <p className="notice warn">Your profile isn't confirmed yet. ApplyAI uses confirmed facts for reliable autofill. <Link to="/profile">Review your profile</Link></p>}
      {nConf > 0 && <p className="notice warn">Your resume and saved profile disagree on {nConf} detail(s). <Link to="/profile">Resolve profile conflicts</Link></p>}
      {profile?.summary?.needs_confirmation > 0 && <p className="notice warn">{profile.summary.needs_confirmation} profile detail(s) are waiting for your confirmation. <Link to="/profile">Confirm details</Link></p>}
      {health && !health.ok && <p className="notice bad">GitHub Copilot CLI isn't available: {health.error}. Check the backend CLI installation and authentication.</p>}

      {metrics && <section className="metric-grid">{metrics.map(([label, value, hint]) => <article className="metric-card" key={label}>
        <span className="muted small">{label}</span><b>{value ?? 0}</b><small className="muted">{hint}</small>
      </article>)}</section>}

      <div className="dashboard-columns">
        <section className="dashboard-section">
          <div className="row between"><div><h2>Recent applications</h2><p className="muted small">Your latest application sessions and their current state.</p></div><Link to="/history">View history</Link></div>
          {apps.length === 0 ? <div className="empty-state"><h3>Your next opportunity starts here</h3><p className="muted">Start with a job URL. The agent will inspect the form, select a suitable resume and ask you to review uncertain answers.</p><Link className="btn primary" to="/apply">Create first application</Link></div> : (
            <div className="application-list">{apps.slice(0, 8).map((a) => <Link className="application-row" to={`/apply/${a.session_id}`} key={a.id}>
              <div className="application-avatar">{(a.company || a.job_title || "J").slice(0, 1).toUpperCase()}</div>
              <div className="application-main"><b>{a.job_title || "Untitled role"}</b><span className="muted small">{a.company || host(a.url)} · {host(a.url)}</span></div>
              <div className="application-state"><StatusChip status={a.status} /><small className="muted">{when(a.created_at)}</small></div>
            </Link>)}</div>
          )}
        </section>

        <section className="readiness-card">
          <h2>Profile readiness</h2>
          <p className="muted small">Improve data quality before running more applications.</p>
          <div className="readiness-stat"><b>{profile?.summary?.confirmed || 0}</b><span>Confirmed facts</span></div>
          <div className="readiness-stat"><b>{profile?.summary?.needs_confirmation || 0}</b><span>Need confirmation</span></div>
          <div className="readiness-stat"><b>{listCount(apps)}</b><span>Applications tracked</span></div>
          <div className="readiness-actions"><Link to="/profile">Review candidate profile</Link><Link to="/profile">Manage resume versions</Link><Link to="/knowledge">Review saved answers</Link></div>
        </section>
      </div>
    </div>
  );
}

function listCount(apps) { return apps.length; }

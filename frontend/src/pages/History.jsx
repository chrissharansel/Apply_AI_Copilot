import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { FlagChips, SourceChip, StatusChip, host, when } from "../ui.jsx";

export default function History() {
  const [apps, setApps] = useState([]);
  const [sel, setSel] = useState(null);
  useEffect(() => { api.get("/applications").then(setApps).catch(() => {}); }, []);
  const open = async (id) => setSel(await api.get(`/applications/${id}`));
  return (
    <div className="page">
      <h1>Application history</h1>
      {apps.length === 0 ? <p className="muted">No applications yet.</p> : (
        <table><thead><tr><th>Role</th><th>Company</th><th>Site</th><th>Resume</th><th>Status</th><th>Date</th></tr></thead><tbody>
          {apps.map((a) => (
            <tr key={a.id} className="click" onClick={() => open(a.id)}>
              <td>{a.job_title || "Untitled role"}</td><td>{a.company}</td><td>{host(a.url)}</td><td>v{a.resume_version}</td><td><StatusChip status={a.status} /></td><td>{when(a.applied_at || a.created_at)}</td>
            </tr>))}
        </tbody></table>)}
      {sel && (
        <section className="detail">
          <div className="row between"><h2>{sel.job_title || "Untitled role"} at {sel.company || "unknown company"}</h2><button className="link" onClick={() => setSel(null)}>Close</button></div>
          <p><a href={sel.url} target="_blank" rel="noreferrer">{sel.url}</a></p>
          {sel.confirmation && <p className="notice good">Confirmation: {sel.confirmation}</p>}
          {sel.errors?.length > 0 && <div className="notice bad">{sel.errors.map((e, i) => <div key={i}>{e.message}</div>)}</div>}
          <Link to={`/apply/${sel.session_id}`}>Open session</Link>
          <h3>Questions answered</h3>
          <table className="fields"><tbody>{sel.questions.map((q) => (
            <tr key={q.id}><td className="lbl">{q.label}</td><td className="val">{q.answer ?? <span className="muted">—</span>}</td><td className="tags"><SourceChip source={q.source} /><FlagChips flags={q.flags} /></td></tr>))}</tbody></table>
        </section>)}
    </div>
  );
}

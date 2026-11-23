import { useEffect, useState } from "react";
import { api } from "../../api";
import { Chip } from "../../ui.jsx";

const yrs = (n) => `${n.toFixed(1)} yrs`;
const mon = (i) => `${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][i % 12]} ${Math.floor(i / 12)}`;

export default function Experience({ p, setP, flash, fail }) {
  const [x, setX] = useState(null);
  const load = () => api.get("/profile/experience").then(setX).catch(fail);
  useEffect(() => { load(); }, [p.updated_at]); // eslint-disable-line
  if (!x) return <p className="muted">Calculating…</p>;
  const setMode = async (mode, stated) => {
    try { setP(await api.put("/profile", { data: { ...p.data, experience_mode: mode, total_experience_years: stated ?? p.data.total_experience_years }, confirm: false })); flash("Saved."); load(); } catch (e) { fail(e); }
  };
  return (
    <div>
      <p className="muted">Calculated from your employment and internship records. Overlapping jobs are counted once, and forms are answered with the category they actually ask for, never overstated.</p>
      <div className="figs small">{[["Total (jobs + internships)", x.total_years], ["Professional (no internships)", x.professional_years], ["Internships", x.internship_years], ["Current role", x.current_role_years]].map(([l, n]) => <div key={l}><b>{n.toFixed(1)}</b><span>{l}</span></div>)}</div>
      {x.warnings.map((w) => <p key={w} className="notice warn">{w}</p>)}
      {x.differs && <p className="notice warn">Your profile says {x.stated_years} years, but your employment records add up to {x.total_years}. Choose which one forms should use below.</p>}
      <div className="card">
        <b>Which total should forms use?</b>
        <div className="choices"><label><input type="radio" checked={x.mode !== "manual"} onChange={() => setMode("calculated")} /> Calculated from my records ({x.total_years.toFixed(1)} yrs)</label>
          <label><input type="radio" checked={x.mode === "manual"} onChange={() => setMode("manual", x.stated_years ?? Math.floor(x.total_years))} /> The number I enter:
            <input style={{ width: 90, marginLeft: 6 }} type="number" step="0.1" disabled={x.mode !== "manual"} defaultValue={x.stated_years ?? ""} onBlur={(e) => e.target.value !== "" && setMode("manual", parseFloat(e.target.value))} /></label></div>
      </div>
      <h2>Records counted</h2>
      {x.records.length === 0 ? <p className="muted">Add employment on the Details tab, with start and end dates.</p> : (
        <table><thead><tr><th>Company</th><th>Title</th><th>Type</th><th>From</th><th>To</th><th>Months</th></tr></thead><tbody>
          {x.records.map((r, i) => <tr key={i}><td>{r.company}</td><td>{r.title}</td><td>{r.kind === "internship" ? <Chip cls="c-blue">internship</Chip> : r.kind.replace("_", " ")}</td><td>{mon(r.start)}</td><td>{r.current ? "Present" : mon(r.end)}</td><td>{r.months}{r.approx ? " ~" : ""}</td></tr>)}
        </tbody></table>)}
      <h2>Experience by skill (estimates)</h2>
      <p className="muted small">Counted from jobs whose title or description mention the skill. These are always offered to you as a suggestion on forms, never typed in silently.</p>
      {x.skills.length === 0 ? <p className="muted">Add skills and describe the tools you used in each job.</p> : <table><tbody>{x.skills.map((s) => <tr key={s.skill}><td>{s.skill}</td><td>{yrs(s.years)}</td><td className="muted">{s.jobs} job(s)</td></tr>)}</tbody></table>}
    </div>
  );
}

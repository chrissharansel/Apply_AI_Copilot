import { api } from "../../api";
import { Chip, FactChip, Field, norm } from "../../ui.jsx";

const SCALARS = [["full_name", "Full name"], ["email", "Email"], ["phone", "Phone"], ["location", "Location (as written on forms)"], ["city", "City"], ["state", "State / province"], ["country", "Country"], ["postal_code", "Postal / PIN code"], ["address", "Street address"], ["current_designation", "Current designation"], ["linkedin", "LinkedIn"], ["github", "GitHub"], ["portfolio", "Portfolio"]];
const PREFS = [["desired_role", "Desired role"], ["expected_salary", "Expected salary"], ["employment_type", "Employment type"], ["notice_period", "Notice period"], ["work_authorization", "Work authorization"], ["availability", "Availability"]];
const LISTS = [
  ["employment", "Employment and internships", "employment", "company", [["company", "Company"], ["title", "Title"], ["kind", "Type", "select", ["full_time", "internship", "contract", "freelance", "part_time"]], ["start_date", "Start (e.g. Jan 2021)"], ["end_date", "End (blank = current)"], ["description", "What you did (tools, skills)"]], { company: "", title: "", kind: "full_time", start_date: "", end_date: "", description: "" }],
  ["education", "Education", "education", "institution", [["degree", "Degree"], ["institution", "Institution"], ["graduation_year", "Year"]], { degree: "", institution: "", graduation_year: "" }],
  ["certifications", "Certifications", "certification", "name", [["name", "Name"], ["issuer", "Issuer"]], { name: "", issuer: "" }],
  ["projects", "Projects", "project", "name", [["name", "Name"], ["description", "Description"], ["technologies", "Technologies (comma separated)", "list"]], { name: "", description: "", technologies: [] }],
  ["other_links", "Other links (LeetCode, Kaggle, repos…)", null, "url", [["label", "Label"], ["url", "URL"]], { label: "", url: "" }],
];

function ListEditor({ title, rows, cols, blank, onChange, chip }) {
  const setCell = (i, k, v) => onChange(rows.map((r, n) => (n === i ? { ...r, [k]: v } : r)));
  return (
    <div className="list-ed">
      <div className="row between"><h3>{title}</h3><button onClick={() => onChange([...rows, { ...blank }])}>Add</button></div>
      {rows.length === 0 && <p className="muted">None added.</p>}
      {rows.map((r, i) => (
        <div className="list-row" key={i}>
          {cols.map(([k, l, t, opts]) => (
            <Field key={k} label={l}>
              {t === "select" ? <select value={r[k] || opts[0]} onChange={(e) => setCell(i, k, e.target.value)}>{opts.map((o) => <option key={o} value={o}>{o.replace("_", " ")}</option>)}</select>
                : <input value={t === "list" ? (r[k] || []).join(", ") : r[k] || ""} onChange={(e) => setCell(i, k, t === "list" ? e.target.value.split(",").map((x) => x.trim()).filter(Boolean) : e.target.value)} />}
            </Field>))}
          <div>{chip(r)}<br /><button className="link danger-t" onClick={() => onChange(rows.filter((_, n) => n !== i))}>Remove</button></div>
        </div>))}
    </div>
  );
}

export default function Details({ p, setP, flash, fail }) {
  const d = p.data, fm = p.fact_meta || {};
  const set = (k, v) => setP({ ...p, data: { ...d, [k]: v } });
  const save = async (confirm) => {
    try { const body = { ...d, total_experience_years: d.total_experience_years === "" ? null : d.total_experience_years }; setP(await api.put("/profile", { data: body, confirm })); flash(confirm ? "Everything on this page is now confirmed. The agent can type it into forms." : "Saved. Edited values stay “typed, not confirmed” until you confirm."); }
    catch (e) { fail(e); }
  };
  const wipe = async () => { if (!confirm("Delete your profile, resumes, saved answers and application history? This can’t be undone.")) return; await api.del("/profile/data"); setP(await api.get("/profile")); flash("Your data was deleted."); };
  const F = ({ path, label, children }) => <Field label={<span className="lbl-row">{label}<FactChip meta={fm[path]} empty={!d[path] || (Array.isArray(d[path]) && !d[path].length)} /></span>}>{children}</Field>;
  return (
    <div>
      <p className="muted small">Review every value, fix what’s wrong, then press “Confirm and save”. Each detail shows where it came from and how sure we are.</p>
      <h2>Personal and professional</h2>
      <div className="grid2">{SCALARS.map(([k, l]) => <F key={k} path={k} label={l}><input value={d[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></F>)}</div>
      <F path="summary" label="Professional summary (used for “tell us about yourself”)"><textarea rows={3} value={d.summary || ""} onChange={(e) => set("summary", e.target.value)} /></F>
      <F path="languages" label="Languages (comma separated)"><input value={(d.languages || []).join(", ")} onChange={(e) => set("languages", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></F>
      <F path="skills" label="Skills (comma separated)"><textarea rows={2} value={(d.skills || []).join(", ")} onChange={(e) => set("skills", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></F>
      {LISTS.map(([k, t, sing, namekey, cols, blank]) => (
        <ListEditor key={k} title={t} rows={d[k] || []} cols={cols} blank={blank} onChange={(v) => set(k, v)}
          chip={(r) => (sing ? <FactChip meta={fm[`${sing}:${norm(r[namekey])}`]} empty={!norm(r[namekey])} /> : <FactChip meta={fm.other_links} empty={!r.url} />)} />))}
      <h2>Preferences</h2>
      <div className="grid2">{PREFS.map(([k, l]) => <F key={k} path={k} label={l}><input value={d[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></F>)}
        <Field label="Preferred locations (comma separated)"><input value={(d.preferred_locations || []).join(", ")} onChange={(e) => set("preferred_locations", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field></div>
      <p className="muted small">Salary and work authorization are sensitive. The agent still asks you before using them on a form, and re-checks volatile ones (notice period, salary) every few months.</p>
      <div className="row sticky"><button className="primary" onClick={() => save(true)}>Confirm and save</button><button onClick={() => save(false)}>Save without confirming</button></div>
      <h2>Your data</h2><button className="danger" onClick={wipe}>Delete all my data</button>
    </div>
  );
}

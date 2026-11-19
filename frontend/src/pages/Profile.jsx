import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Chip, Field, when } from "../ui.jsx";

const SCALARS = [["full_name", "Full name"], ["email", "Email"], ["phone", "Phone"], ["location", "Location (as written on forms)"], ["city", "City"], ["state", "State / province"], ["country", "Country"], ["postal_code", "Postal / PIN code"], ["address", "Street address"], ["current_designation", "Current designation"], ["total_experience_years", "Total experience (years)", "number"], ["linkedin", "LinkedIn"], ["github", "GitHub"], ["portfolio", "Portfolio"]];
const PREFS = [["desired_role", "Desired role"], ["expected_salary", "Expected salary"], ["employment_type", "Employment type"], ["notice_period", "Notice period"], ["work_authorization", "Work authorization"], ["availability", "Availability"]];
const LISTS = [
  ["other_links", "Other links (LeetCode, Kaggle, project repos…)", [["label", "Label"], ["url", "URL"]], { label: "", url: "" }],
  ["education", "Education", [["degree", "Degree"], ["institution", "Institution"], ["graduation_year", "Year"]], { degree: "", institution: "", graduation_year: "" }],
  ["employment", "Employment", [["company", "Company"], ["title", "Title"], ["start_date", "Start"], ["end_date", "End (blank = current)"], ["description", "What you did"]], { company: "", title: "", start_date: "", end_date: "", description: "" }],
  ["certifications", "Certifications", [["name", "Name"], ["issuer", "Issuer"]], { name: "", issuer: "" }],
  ["projects", "Projects", [["name", "Name"], ["description", "Description"], ["technologies", "Technologies (comma separated)", "list"]], { name: "", description: "", technologies: [] }],
];

function ListEditor({ title, rows, cols, blank, onChange }) {
  const setCell = (i, k, v) => onChange(rows.map((r, n) => (n === i ? { ...r, [k]: v } : r)));
  return (
    <div className="list-ed">
      <div className="row between"><h3>{title}</h3><button onClick={() => onChange([...rows, { ...blank }])}>Add</button></div>
      {rows.length === 0 && <p className="muted">None added.</p>}
      {rows.map((r, i) => (
        <div className="list-row" key={i}>
          {cols.map(([k, l, t]) => (
            <Field key={k} label={l}>
              <input value={t === "list" ? (r[k] || []).join(", ") : r[k] || ""}
                onChange={(e) => setCell(i, k, t === "list" ? e.target.value.split(",").map((x) => x.trim()).filter(Boolean) : e.target.value)} />
            </Field>))}
          <button className="link danger-t" onClick={() => onChange(rows.filter((_, n) => n !== i))}>Remove</button>
        </div>))}
    </div>
  );
}

export default function Profile() {
  const [p, setP] = useState(null);
  const [resumes, setResumes] = useState([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const file = useRef(null);
  const load = async () => { setP(await api.get("/profile")); setResumes(await api.get("/resumes")); };
  useEffect(() => { load().catch((e) => setErr(e.message)); }, []);
  if (!p) return <div className="page"><p className="muted">{err || "Loading…"}</p></div>;
  const d = p.data;
  const set = (k, v) => setP({ ...p, data: { ...d, [k]: v } });
  const save = async (confirm) => {
    setErr(""); setMsg("");
    try { const body = { ...d, total_experience_years: d.total_experience_years === "" ? null : d.total_experience_years }; setP(await api.put("/profile", { data: body, confirm })); setMsg(confirm ? "Profile confirmed. The agent can use it now." : "Draft saved. Confirm it before applying."); }
    catch (e) { setErr(e.message); }
  };
  const upload = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    setErr(""); setMsg("Reading your resume…");
    try { const r = await api.upload("/resumes", f); await load(); setMsg(r.warning || "Resume added. Check the extracted details below, then confirm."); }
    catch (e2) { setErr(e2.message); setMsg(""); } finally { file.current.value = ""; }
  };
  const [conf, setConf] = useState({});
  const fetchLinks = async (overwrite = false) => {
    setErr(""); setMsg("");
    try {
      const r = await api.post(`/profile/refresh-links?overwrite=${overwrite}`);
      setP(r.profile); setConf(r.conflicts || {});
      setMsg(r.links_in_file === 0 ? "No clickable links were found in your resume file." : r.added.length ? `Found in your resume: ${r.added.join(", ")}. Review and confirm below.` : "Nothing new: your profile already has the links from your resume.");
    } catch (e) { setErr(e.message); }
  };
  const resumeAct = async (fn) => { try { await fn(); await load(); } catch (e) { setErr(e.message); } };
  const wipe = async () => {
    if (!confirm("Delete your profile, resumes, saved answers and application history? This can’t be undone.")) return;
    await api.del("/profile/data"); await load(); setMsg("Your data was deleted.");
  };
  return (
    <div className="page narrow">
      <div className="row between"><h1>Profile</h1>{p.confirmed ? <Chip cls="c-green">Confirmed {when(p.confirmed_at)}</Chip> : <Chip cls="c-amber">Not confirmed</Chip>}</div>
      {!p.confirmed && <p className="notice warn">Extracted details can be wrong. Check each section, then press “Confirm and save”. The agent only uses confirmed information.</p>}
      {msg && <p className="notice good">{msg}</p>}{err && <p className="error">{err}</p>}

      <h2>Resumes</h2>
      <div className="row"><input ref={file} type="file" accept=".pdf,.docx" onChange={upload} /></div>
      <table><tbody>{resumes.map((r) => (
        <tr key={r.id}><td>Version {r.version}</td><td>{r.filename}</td><td>{r.active ? <Chip cls="c-green">Used for applications</Chip> : <button className="link" onClick={() => resumeAct(() => api.post(`/resumes/${r.id}/activate`))}>Use this one</button>}</td>
          <td><button className="link" onClick={() => resumeAct(() => api.post(`/profile/from-resume/${r.id}`))}>Load its details into profile</button></td>
          <td><button className="link" title="Re-read the file, including clickable links, headers and text boxes" onClick={() => resumeAct(() => api.post(`/resumes/${r.id}/reparse`))}>Re-read</button></td>
          <td><button className="link danger-t" onClick={() => resumeAct(() => api.del(`/resumes/${r.id}`))}>Delete</button></td></tr>))}</tbody></table>
      <div className="row wrap"><button onClick={() => fetchLinks(false)}>Fetch LinkedIn / GitHub / links from my resume</button>
        <span className="muted small">Reads the clickable labels in your PDF/DOCX, even when only “LinkedIn” is visible. No AI involved.</span></div>
      {Object.entries(conf).map(([k, u]) => <p key={k} className="notice warn">Your resume links {k} to <b>{u}</b>, which differs from your profile. <button className="link" onClick={() => fetchLinks(true)}>Use the resume’s version</button></p>)}

      <h2>Personal and professional</h2>
      <div className="grid2">{SCALARS.map(([k, l, t]) => <Field key={k} label={l}><input type={t || "text"} value={d[k] ?? ""} onChange={(e) => set(k, t === "number" ? e.target.value : e.target.value)} /></Field>)}</div>
      <Field label="Professional summary (used for “tell us about yourself”)"><textarea rows={3} value={d.summary || ""} onChange={(e) => set("summary", e.target.value)} /></Field>
      <Field label="Languages (comma separated)"><input value={(d.languages || []).join(", ")} onChange={(e) => set("languages", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field>
      <Field label="Skills (comma separated)"><textarea rows={2} value={(d.skills || []).join(", ")} onChange={(e) => set("skills", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field>
      {LISTS.map(([k, t, cols, blank]) => <ListEditor key={k} title={t} rows={d[k] || []} cols={cols} blank={blank} onChange={(v) => set(k, v)} />)}

      <h2>Preferences</h2>
      <div className="grid2">{PREFS.map(([k, l]) => <Field key={k} label={l}><input value={d[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></Field>)}
        <Field label="Preferred locations (comma separated)"><input value={(d.preferred_locations || []).join(", ")} onChange={(e) => set("preferred_locations", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field></div>
      <p className="muted">Salary and work authorization are sensitive. The agent will still ask you before using them on a form.</p>

      <div className="row sticky"><button className="primary" onClick={() => save(true)}>Confirm and save</button><button onClick={() => save(false)}>Save draft</button></div>
      <h2>Your data</h2>
      <button className="danger" onClick={wipe}>Delete all my data</button>
    </div>
  );
}

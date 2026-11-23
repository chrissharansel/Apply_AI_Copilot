import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { Chip, Field } from "../../ui.jsx";

export default function Resumes({ p, setP, flash, fail, goto, reload }) {
  const [list, setList] = useState([]);
  const [meta, setMeta] = useState({ label: "", category: "", keywords: "" });
  const [edit, setEdit] = useState(null);
  const [conf, setConf] = useState({});
  const [job, setJob] = useState({ title: "", description: "" });
  const [rec, setRec] = useState(null);
  const [busy, setBusy] = useState(false);
  const file = useRef(null);
  const load = () => api.get("/resumes").then(setList).catch(fail);
  useEffect(() => { load(); }, []); // eslint-disable-line
  const act = async (fn) => { try { await fn(); await load(); await reload(); } catch (e) { fail(e); } };
  const upload = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    flash("Reading your resume, including its clickable links…"); setBusy(true);
    try {
      const r = await api.upload("/resumes", f, meta);
      setMeta({ label: "", category: "", keywords: "" }); await load(); await reload();
      flash(r.warning || (r.conflicts ? `Resume added. ${r.conflicts} difference(s) with your saved profile need a decision (Conflicts tab).` : "Resume added."));
    } catch (e2) { fail(e2); } finally { setBusy(false); file.current.value = ""; }
  };
  const fetchLinks = async (overwrite = false) => {
    try {
      const r = await api.post(`/profile/refresh-links?overwrite=${overwrite}`); setP(r.profile); setConf(r.conflicts || {});
      flash(r.links_in_file === 0 ? "No clickable links were found in your resume file." : r.added.length ? `Found in your resume: ${r.added.join(", ")}. They’re marked “from resume link” until you confirm them.` : "Nothing new: your profile already has the links from your resume.");
    } catch (e) { fail(e); }
  };
  const saveMeta = () => act(async () => { await api.put(`/resumes/${edit.id}`, { label: edit.label, category: edit.category, keywords: edit.keywords.split(",").map((x) => x.trim()).filter(Boolean) }); setEdit(null); });
  const recommend = async () => { setRec(null); try { setRec(await api.post("/resumes/recommend", job)); } catch (e) { fail(e); } };
  return (
    <div>
      <h2>Your resumes</h2>
      <p className="muted small">Keep one resume per job category (for example Python Developer, Java Developer, AI Engineer). When you apply with “Auto-pick”, ApplyAI chooses the best one for each job description.</p>
      <div className="card">
        <div className="grid2">
          <Field label="Label (e.g. Python Developer)"><input value={meta.label} onChange={(e) => setMeta({ ...meta, label: e.target.value })} placeholder="Leave blank to detect from the resume" /></Field>
          <Field label="Category (optional)"><input value={meta.category} onChange={(e) => setMeta({ ...meta, category: e.target.value })} placeholder="Backend, Data, Full stack…" /></Field>
        </div>
        <Field label="Keywords that should pull this resume in (comma separated, optional)"><input value={meta.keywords} onChange={(e) => setMeta({ ...meta, keywords: e.target.value })} placeholder="django, fastapi, pandas" /></Field>
        <input ref={file} type="file" accept=".pdf,.docx" onChange={upload} disabled={busy} />
      </div>
      {list.map((r) => (
        <div className="card" key={r.id}>
          <div className="lbl-row"><b>{edit?.id === r.id ? "Editing" : r.label}</b>
            <span>{r.category && <Chip>{r.category}</Chip>}{r.active ? <Chip cls="c-green">Default</Chip> : <button className="link" onClick={() => act(() => api.post(`/resumes/${r.id}/activate`))}>Make default</button>}</span></div>
          <p className="muted small">v{r.version}, {r.filename}{r.keywords?.length ? `, keywords: ${r.keywords.join(", ")}` : ""}</p>
          {edit?.id === r.id ? (
            <div className="grid2"><Field label="Label"><input value={edit.label} onChange={(e) => setEdit({ ...edit, label: e.target.value })} /></Field>
              <Field label="Category"><input value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} /></Field>
              <Field label="Keywords"><input value={edit.keywords} onChange={(e) => setEdit({ ...edit, keywords: e.target.value })} /></Field>
              <div className="row"><button className="primary" onClick={saveMeta}>Save</button><button onClick={() => setEdit(null)}>Cancel</button></div></div>
          ) : (
            <div className="row wrap">
              <button className="link" onClick={() => setEdit({ id: r.id, label: r.label, category: r.category || "", keywords: (r.keywords || []).join(", ") })}>Edit label</button>
              <button className="link" onClick={() => act(async () => { const x = await api.post(`/resumes/${r.id}/reparse`); flash(x.conflicts ? `Re-read. ${x.conflicts} difference(s) with your profile.` : "Re-read."); })} title="Re-read the file including links, headers and text boxes">Re-read</button>
              <button className="link" onClick={() => act(async () => { setP(await api.post(`/profile/from-resume/${r.id}`)); flash("Loaded into your profile as unconfirmed details."); goto("details"); })}>Load its details into my profile</button>
              <button className="link danger-t" onClick={() => act(() => api.del(`/resumes/${r.id}`))}>Delete</button>
            </div>)}
        </div>))}
      <div className="row wrap"><button onClick={() => fetchLinks(false)}>Fetch LinkedIn / GitHub / links from my resume</button>
        <span className="muted small">Reads the clickable labels in your file. No AI involved.</span></div>
      {Object.entries(conf).map(([k, u]) => <p key={k} className="notice warn">Your resume links {k} to <b>{u}</b>, which differs from your profile. <button className="link" onClick={() => fetchLinks(true)}>Use the resume’s version</button></p>)}

      <h2>Which resume fits a job?</h2>
      <div className="card">
        <Field label="Job title"><input value={job.title} onChange={(e) => setJob({ ...job, title: e.target.value })} placeholder="Senior Python Developer" /></Field>
        <Field label="Job description"><textarea rows={4} value={job.description} onChange={(e) => setJob({ ...job, description: e.target.value })} placeholder="Paste the posting here" /></Field>
        <button disabled={!job.title && !job.description} onClick={recommend}>Recommend a resume</button>
        {rec && <div className="rank"><p><b>Best match: {rec.label}</b> <Chip cls={rec.confidence === "high" ? "c-green" : rec.confidence === "medium" ? "c-amber" : "c-grey"}>{rec.confidence} confidence</Chip></p>
          <p className="muted small">{rec.reason}</p>
          {rec.ranking.map((x) => <div key={x.id}><span className="small">{x.label}: {Math.round(x.score * 100)}% {x.matched.length > 0 && <span className="muted">(matched: {x.matched.slice(0, 6).join(", ")})</span>}</span><div className="bar"><i style={{ width: `${Math.min(100, x.score * 150)}%` }} /></div></div>)}</div>}
      </div>
    </div>
  );
}

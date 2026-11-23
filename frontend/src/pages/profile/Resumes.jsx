import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { Chip, Field } from "../../ui.jsx";

const JOB_TYPES = [
  ["software_development", "Software development"], ["data_ai", "Data / AI / ML"],
  ["devops_cloud", "DevOps / Cloud"], ["qa_testing", "QA / Testing"],
  ["product", "Product"], ["design", "Design"], ["business", "Business"], ["other", "Other"],
];

const blankMeta = () => ({
  label: "", category: "", job_type: "other", target_role: "",
  keywords: "", effective_from: "", effective_until: "",
});

export default function Resumes({ p, setP, flash, fail, goto, reload }) {
  const [list, setList] = useState([]);
  const [meta, setMeta] = useState(blankMeta);
  const [edit, setEdit] = useState(null);
  const [conf, setConf] = useState({});
  const [job, setJob] = useState({ title: "", description: "", job_type: "other" });
  const [rec, setRec] = useState(null);
  const [busy, setBusy] = useState(false);
  const file = useRef(null);
  const load = () => api.get("/resumes").then(setList).catch(fail);
  useEffect(() => { load(); }, []); // eslint-disable-line

  const act = async (fn) => {
    try { await fn(); await load(); await reload(); }
    catch (e) { fail(e); }
  };

  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    flash("Reading your resume, including clickable links…");
    setBusy(true);
    try {
      const r = await api.upload("/resumes", f, meta);
      setMeta(blankMeta());
      await load(); await reload();
      flash(r.warning || (r.conflicts
        ? `Resume version added. ${r.conflicts} profile difference(s) need review.`
        : "Resume version added."));
    } catch (e2) { fail(e2); }
    finally { setBusy(false); if (file.current) file.current.value = ""; }
  };

  const saveMeta = async () => {
    if (!edit) return;
    await act(async () => {
      await api.put(`/resumes/${edit.id}`, {
        label: edit.label, category: edit.category, job_type: edit.job_type,
        target_role: edit.target_role, effective_from: edit.effective_from,
        effective_until: edit.effective_until,
        keywords: edit.keywords.split(",").map((x) => x.trim()).filter(Boolean),
      });
      setEdit(null);
      flash("Resume version details updated.");
    });
  };

  const recommend = async () => {
    setRec(null);
    try { setRec(await api.post("/resumes/recommend", job)); }
    catch (e) { fail(e); }
  };

  const familyCount = new Set(list.map((r) => r.job_type || "other")).size;
  const groupedResumes = JOB_TYPES.map(([type, label]) => ({
    type, label, items: list.filter((r) => (r.job_type || "other") === type)
  })).filter((group) => group.items.length);

  return (
    <div className="resume-library">
      <div className="row between">
        <div><h2>Resume library</h2><p className="muted small">Maintain separate, dated resume versions for each job family. The matcher weighs role fit, skills, target title, family default and effective dates.</p></div>
        <Chip cls="c-blue">{list.length} versions · {familyCount} job families</Chip>
      </div>

      <section className="card resume-upload">
        <h3>Add a resume version</h3>
        <p className="muted small">Upload a new version whenever your experience changes. Older versions remain available for comparison.</p>
        <div className="grid2">
          <Field label="Version label"><input value={meta.label} onChange={(e) => setMeta({ ...meta, label: e.target.value })} placeholder="e.g. Python Developer — Nov 2026" /></Field>
          <Field label="Job family"><select value={meta.job_type} onChange={(e) => setMeta({ ...meta, job_type: e.target.value })}>{JOB_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Specialization"><input value={meta.category} onChange={(e) => setMeta({ ...meta, category: e.target.value })} placeholder="Backend, Full stack, GenAI…" /></Field>
          <Field label="Target job title"><input value={meta.target_role} onChange={(e) => setMeta({ ...meta, target_role: e.target.value })} placeholder="Python Developer" /></Field>
          <Field label="Effective from"><input type="date" value={meta.effective_from} onChange={(e) => setMeta({ ...meta, effective_from: e.target.value })} /></Field>
          <Field label="Effective until"><input type="date" value={meta.effective_until} onChange={(e) => setMeta({ ...meta, effective_until: e.target.value })} /></Field>
        </div>
        <Field label="Matching keywords (comma separated)"><input value={meta.keywords} onChange={(e) => setMeta({ ...meta, keywords: e.target.value })} placeholder="java, spring boot, microservices" /></Field>
        <div className="row between wrap"><span className="muted small">PDF or DOCX · up to your configured upload limit</span>
          <label className="btn primary">{busy ? "Processing…" : "Choose resume"}<input ref={file} type="file" accept=".pdf,.docx" onChange={upload} disabled={busy} hidden /></label>
        </div>
      </section>

      <div className="resume-version-list">
        {groupedResumes.map((group) => <section className="resume-family" key={group.type}>
          <div className="row between"><h3>{group.label}</h3><Chip>{group.items.length} version(s)</Chip></div>
          {group.items.map((r) => (
          <article className="card resume-version" key={r.id}>
            <div className="row between wrap">
              <div><div className="row wrap"><h3>{r.label || r.filename}</h3>
                {r.active && <Chip cls="c-green">Global default</Chip>}
                {r.job_type_active && <Chip cls="c-blue">Family default</Chip>}
              </div><p className="muted small">{r.filename} · Overall v{r.version} · {r.job_type || "other"} v{r.family_version || r.version}</p></div>
              <div className="row wrap">
                {!r.job_type_active && <button onClick={() => act(() => api.post(`/resumes/${r.id}/activate-family`))}>Set family default</button>}
                {!r.active && <button onClick={() => act(() => api.post(`/resumes/${r.id}/activate`))}>Set global default</button>}
              </div>
            </div>
            <div className="resume-meta">
              {r.category && <Chip>{r.category}</Chip>}
              {r.target_role && <Chip cls="c-blue">{r.target_role}</Chip>}
              {r.effective_from && <Chip>From {r.effective_from}</Chip>}
              {r.effective_until && <Chip>Until {r.effective_until}</Chip>}
              {r.created_at && <span className="muted small">Uploaded {new Date(r.created_at).toLocaleDateString()}</span>}
            </div>
            {r.keywords?.length > 0 && <p className="muted small">Keywords: {r.keywords.join(", ")}</p>}
            {edit?.id === r.id ? (
              <div className="edit-resume grid2">
                <Field label="Label"><input value={edit.label} onChange={(e) => setEdit({ ...edit, label: e.target.value })} /></Field>
                <Field label="Job family"><select value={edit.job_type} onChange={(e) => setEdit({ ...edit, job_type: e.target.value })}>{JOB_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
                <Field label="Specialization"><input value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} /></Field>
                <Field label="Target title"><input value={edit.target_role} onChange={(e) => setEdit({ ...edit, target_role: e.target.value })} /></Field>
                <Field label="Effective from"><input type="date" value={edit.effective_from} onChange={(e) => setEdit({ ...edit, effective_from: e.target.value })} /></Field>
                <Field label="Effective until"><input type="date" value={edit.effective_until} onChange={(e) => setEdit({ ...edit, effective_until: e.target.value })} /></Field>
                <Field label="Keywords"><input value={edit.keywords} onChange={(e) => setEdit({ ...edit, keywords: e.target.value })} /></Field>
                <div className="row"><button className="primary" onClick={saveMeta}>Save version</button><button onClick={() => setEdit(null)}>Cancel</button></div>
              </div>
            ) : (
              <div className="row wrap">
                <button className="link" onClick={() => setEdit({
                  id: r.id, label: r.label || "", category: r.category || "", job_type: r.job_type || "other",
                  target_role: r.target_role || "", effective_from: r.effective_from || "",
                  effective_until: r.effective_until || "", keywords: (r.keywords || []).join(", "),
                })}>Edit version metadata</button>
                <button className="link" onClick={() => act(async () => {
                  const x = await api.post(`/resumes/${r.id}/reparse`);
                  flash(x.conflicts ? `Re-read complete. ${x.conflicts} profile difference(s).` : "Resume re-read complete.");
                })}>Re-read file</button>
                <button className="link" onClick={() => act(async () => {
                  setP(await api.post(`/profile/from-resume/${r.id}`));
                  flash("Resume facts loaded as unconfirmed details."); goto("details");
                })}>Review extracted facts</button>
                <button className="link danger-t" onClick={() => act(() => api.del(`/resumes/${r.id}`))}>Delete version</button>
              </div>
            )}
          </article>
          ))}
        </section>)}
        {!list.length && <p className="muted">No resume versions yet. Upload your first resume above.</p>}
      </div>

      <section className="card resume-match">
        <h3>Match a resume to a job</h3>
        <p className="muted small">The recommendation is explainable: job-family alignment, title match, skills coverage, keywords and version timing all contribute.</p>
        <Field label="Job title"><input value={job.title} onChange={(e) => setJob({ ...job, title: e.target.value })} placeholder="Senior Python Developer" /></Field>
        <Field label="Job family"><select value={job.job_type} onChange={(e) => setJob({ ...job, job_type: e.target.value })}>{JOB_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        <Field label="Job description"><textarea rows={5} value={job.description} onChange={(e) => setJob({ ...job, description: e.target.value })} placeholder="Paste the job description…" /></Field>
        <button className="primary" disabled={!job.title && !job.description} onClick={recommend}>Compare my resume versions</button>
        {rec && <div className="rank">
          <p><b>Recommended: {rec.label}</b> <Chip cls={rec.confidence === "high" ? "c-green" : rec.confidence === "medium" ? "c-amber" : "c-grey"}>{rec.confidence} confidence</Chip></p>
          <p className="muted small">{rec.reason}</p>
          {rec.ranking.map((x) => <div className="resume-rank" key={x.id}>
            <div className="row between"><span className="small"><b>{x.label}</b> · {Math.round(x.score * 100)}%</span>
              <span className="muted small">{x.job_type_match ? "Job family match" : "Skills/title match"}</span></div>
            <div className="bar"><i style={{ width: `${Math.min(100, x.score * 100)}%` }} /></div>
            <span className="muted small">Evidence: {x.matched.slice(0, 8).join(", ") || "No strong keyword overlap"}</span>
          </div>)}
        </div>}
      </section>

      <div className="row wrap"><button onClick={async () => {
        try {
          const r = await api.post("/profile/refresh-links?overwrite=false");
          setP(r.profile); setConf(r.conflicts || {});
          flash(r.links_in_file === 0 ? "No clickable links found." : `Resume links checked. ${r.added?.length || 0} new link(s) found.`);
        } catch (e) { fail(e); }
      }}>Refresh links from profile resume</button><span className="muted small">Clickable LinkedIn, GitHub and portfolio links are read from the file itself.</span></div>
      {Object.entries(conf).map(([k, u]) => <p key={k} className="notice warn">Resume link {k} differs from your profile: <b>{u}</b>.</p>)}
    </div>
  );
}

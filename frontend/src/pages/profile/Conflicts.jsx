import { useEffect, useState } from "react";
import { api } from "../../api";
import { Chip } from "../../ui.jsx";

const KIND = { different: ["Different", "c-rose"], new_in_resume: ["Only on resume", "c-amber"], missing_in_resume: ["Only in profile", "c-grey"] };

export default function Conflicts({ p, setP, flash, fail, onChange }) {
  const [resumes, setResumes] = useState([]);
  const [rid, setRid] = useState("");
  const [data, setData] = useState(null);
  const [pick, setPick] = useState({});
  const load = async (id = rid) => { try { const r = await api.get(`/profile/conflicts${id ? `?resume_id=${id}` : ""}`); setData(r); setPick({}); if (!id && r.resume) setRid(r.resume.id); } catch (e) { fail(e); } };
  useEffect(() => { api.get("/resumes").then(setResumes).catch(fail); load(""); }, []); // eslint-disable-line
  if (!data) return <p className="muted">Comparing…</p>;
  const items = data.conflicts, open = items.filter((c) => c.kind !== "missing_in_resume");
  const choose = (id, v) => setPick({ ...pick, [id]: { ...pick[id], ...v } });
  const apply = async () => {
    const resolutions = Object.entries(pick).filter(([, v]) => v.choice).map(([id, v]) => ({ id, choice: v.choice, value: v.value || null }));
    try { setP(await api.post("/profile/conflicts/resolve", { resume_id: rid || null, resolutions })); flash("Saved. Values you decided on are now confirmed."); await load(); onChange && onChange(); } catch (e) { fail(e); }
  };
  return (
    <div>
      <p className="muted">ApplyAI compares what your resume says with your saved profile. Nothing is changed until you decide. Pick the correct value for each difference.</p>
      <div className="row"><span className="small">Compare with</span><select style={{ width: "auto" }} value={rid} onChange={(e) => { setRid(e.target.value); load(e.target.value); }}>
        {resumes.map((r) => <option key={r.id} value={r.id}>{r.label || r.filename}</option>)}</select></div>
      {!data.resume ? <p className="muted">Upload a resume and create a profile first.</p> : open.length === 0 && <p className="notice good">No differences. Your profile and this resume agree.</p>}
      {items.map((c) => (
        <div key={c.id} className={`card sev-${c.severity}`}>
          <div className="lbl-row"><b>{c.label}</b><span><Chip cls={KIND[c.kind][1]}>{KIND[c.kind][0]}</Chip>{c.severity === "high" && <Chip cls="c-rose">Important</Chip>}</span></div>
          <div className="cmp"><div><small>Your profile</small>{c.profile || <span className="muted">(empty)</span>}</div><div><small>This resume</small>{c.resume}</div></div>
          {c.kind !== "missing_in_resume" && (
            <div className="choices">
              <label><input type="radio" name={c.id} checked={pick[c.id]?.choice === "profile"} onChange={() => choose(c.id, { choice: "profile" })} /> {c.kind === "new_in_resume" ? "Ignore" : "Keep my profile"}</label>
              <label><input type="radio" name={c.id} checked={pick[c.id]?.choice === "resume"} onChange={() => choose(c.id, { choice: "resume" })} /> {c.kind === "new_in_resume" ? "Add to my profile" : "Use the resume’s"}</label>
              {c.kind === "different" && c.target.type !== "item" || c.target.field !== "*" && c.kind === "different" ? <label><input type="radio" name={c.id} checked={pick[c.id]?.choice === "custom"} onChange={() => choose(c.id, { choice: "custom" })} /> Neither, it’s <input type="text" value={pick[c.id]?.value || ""} onChange={(e) => choose(c.id, { choice: "custom", value: e.target.value })} /></label> : null}
            </div>)}
        </div>))}
      {open.length > 0 && <div className="row sticky"><button className="primary" disabled={!Object.values(pick).some((v) => v.choice)} onClick={apply}>Apply my decisions</button><span className="muted small">{Object.values(pick).filter((v) => v.choice).length} of {open.length} decided</span></div>}
    </div>
  );
}

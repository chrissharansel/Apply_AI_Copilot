import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Chip, FlagChips, SourceChip, StatusChip, host, when } from "../ui.jsx";

export default function Apply() {
  const { id } = useParams();
  return id ? <Session id={id} /> : <Start />;
}

function Start() {
  const nav = useNavigate();
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState([]);
  useEffect(() => { api.get("/agent/sessions").then(setRecent).catch(() => {}); }, []);
  const go = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try { const r = await api.post("/agent/sessions", { url }); nav(`/apply/${r.id}`); }
    catch (e2) { setErr(e2.message); setBusy(false); }
  };
  return (
    <div className="page narrow">
      <h1>Apply to a job</h1>
      <form onSubmit={go} className="urlbar">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://company.com/careers/apply/software-developer" required autoFocus />
        <button className="primary" disabled={busy}>{busy ? "Starting…" : "Start"}</button>
      </form>
      {err && <p className="error">{err}</p>}
      <p className="muted">A browser window opens on your computer so you can watch, and step in for logins or CAPTCHAs. The agent never submits without your approval.</p>
      {recent.length > 0 && <>
        <h2>Recent sessions</h2>
        <ul className="plain">{recent.slice(0, 6).map((s) => (
          <li key={s.id}><Link to={`/apply/${s.id}`}>{s.job?.title || host(s.url)}</Link> <StatusChip status={s.status} /> <span className="muted">{when(s.created_at)}</span></li>
        ))}</ul>
      </>}
    </div>
  );
}

function Session({ id }) {
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => { try { setS(await api.get(`/agent/sessions/${id}`)); } catch (e) { setErr(e.message); } }, [id]);
  useEffect(() => { load(); const t = setInterval(load, 2000); return () => clearInterval(t); }, [load]);
  if (!s) return <div className="page">{err ? <p className="error">{err}</p> : <p className="muted">Loading…</p>}</div>;

  const open = (s.pending_questions || []).filter((q) => q.status === "open");
  const review = s.status === "Ready for Review";
  const act = async (path) => { try { await api.post(`/agent/sessions/${id}/${path}`); load(); } catch (e) { setErr(e.message); } };
  return (
    <div className="page">
      <div className="row between">
        <div>
          <h1>{s.job?.title || "Reading the job posting…"}</h1>
          <p className="muted">{s.job?.company ? `${s.job.company} on ` : ""}<a href={s.url} target="_blank" rel="noreferrer">{host(s.url)}</a></p>
        </div>
        <div className="row"><StatusChip status={s.status} />
          {s.resumable && <button onClick={() => act("resume")}>Resume</button>}
          {!["Submitted", "Cancelled", "Failed"].includes(s.status) && <button className="danger" onClick={() => act("cancel")}>Cancel</button>}
        </div>
      </div>
      <div className="bar"><i style={{ width: `${s.progress || 0}%` }} /></div>
      {s.error && <p className="notice bad">{s.error}</p>}
      {s.status === "Submitted" && <p className="notice good">Submitted. {s.confirmation}</p>}
      {err && <p className="error">{err}</p>}

      {review ? <Review s={s} reload={load} /> : (
        <div className="split">
          <section><h2>Fields</h2><FieldTable items={s.results || []} /><Snapshot id={id} /></section>
          <Chat s={s} open={open} reload={load} />
        </div>
      )}
    </div>
  );
}

function FieldTable({ items }) {
  const rows = items.filter((i) => i.status !== "planned" || i.action === "ask");
  if (!rows.length) return <p className="muted">Fields appear here as the agent finds and fills them.</p>;
  return (
    <table className="fields"><tbody>
      {rows.map((i, n) => (
        <tr key={i.sk || n}>
          <td className="lbl">{i.label}{i.required && <span className="req"> required</span>}</td>
          <td className="val">{i.kind === "file" ? i.value : i.status === "planned" ? <span className="muted">Waiting for your answer</span> : (i.value ?? <span className="muted">{i.note || "Empty"}</span>)}</td>
          <td className="tags"><SourceChip source={i.source} /><FlagChips flags={i.flags} />{i.status === "skipped" && <Chip>Skipped</Chip>}{i.status === "manual" && <Chip cls="c-green">Done by you</Chip>}</td>
        </tr>
      ))}
    </tbody></table>
  );
}

function Snapshot({ id }) {
  const [src, setSrc] = useState(null);
  const [err, setErr] = useState("");
  const get = async () => { setErr(""); try { setSrc(await api.blob(`/agent/sessions/${id}/screenshot`)); } catch (e) { setErr(e.message); } };
  return (
    <div className="snap">
      <button onClick={get}>{src ? "Refresh browser snapshot" : "Show browser snapshot"}</button>
      {err && <span className="muted"> {err}</span>}
      {src && <img src={src} alt="Current state of the application page" />}
    </div>
  );
}

function Chat({ s, open, reload }) {
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [s.messages?.length, open.length]);
  return (
    <section className="chat">
      <h2>Agent</h2>
      <div className="msgs">
        {(s.messages || []).map((m) => (
          <div key={m.id} className={`msg ${m.role} ${m.kind}`}>{m.text}</div>
        ))}
        {open.map((q) => <QuestionCard key={q.qid} q={q} sid={s.id} reload={reload} />)}
        <div ref={end} />
      </div>
    </section>
  );
}

const trunc = (t, n = 60) => (t.length > n ? t.slice(0, n) + "…" : t);

function QuestionCard({ q, sid, reload }) {
  const multi = q.kind === "checkbox_group";
  const [val, setVal] = useState(multi ? [] : "");
  const [stage, setStage] = useState("answer");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const send = async (payload) => {
    setBusy(true); setErr("");
    try { await api.post(`/agent/sessions/${sid}/answers`, { qid: q.qid, ...payload }); reload(); }
    catch (e) { setErr(e.message); setBusy(false); }
  };
  if (q.manual) return <div className="qcard"><button className="primary" disabled={busy} onClick={() => send({ action: "done" })}>Done, continue</button>{err && <p className="error">{err}</p>}</div>;

  const has = multi ? val.length > 0 : String(val).trim() !== "";
  const shown = multi ? val.join(", ") : val;
  if (stage === "save") return (
    <div className="qcard">
      <p className="muted">Answer: <b>{trunc(String(shown), 120)}</b></p>
      <p>Save this for future applications?</p>
      {q.sensitive && <p className="muted">This is a sensitive question. Saved answers are only reused when the question matches exactly, and they ask you to reconfirm after a while.</p>}
      <div className="row wrap">
        <button className="primary" disabled={busy} onClick={() => send({ answer: val, save: "reusable" })}>Yes, save it</button>
        <button disabled={busy} onClick={() => send({ answer: val, save: "job_only" })}>Only this application</button>
        <button disabled={busy} onClick={() => send({ answer: val, save: "no" })}>Don’t save</button>
        <button className="link" onClick={() => setStage("answer")}>Change answer</button>
      </div>{err && <p className="error">{err}</p>}
    </div>
  );
  return (
    <div className="qcard">
      {q.suggested && <button className="suggest" onClick={() => { setVal(q.suggested); setStage("save"); }}>Use “{trunc(q.suggested)}”</button>}
      {q.options.length > 0 ? (multi ? (
        <div className="checks">{q.options.map((o) => (
          <label key={o}><input type="checkbox" checked={val.includes(o)} onChange={(e) => setVal(e.target.checked ? [...val, o] : val.filter((x) => x !== o))} /> {o}</label>))}</div>
      ) : (
        <div className="row wrap">{q.options.slice(0, 8).map((o) => <button key={o} className={val === o ? "on" : ""} onClick={() => setVal(o)}>{o}</button>)}
          {q.options.length > 8 && <select value={val} onChange={(e) => setVal(e.target.value)}><option value="">More options…</option>{q.options.map((o) => <option key={o}>{o}</option>)}</select>}</div>
      )) : q.kind === "textarea" ? <textarea rows={4} value={val} onChange={(e) => setVal(e.target.value)} placeholder="Your answer" />
        : <input type={q.kind === "date" ? "date" : "text"} value={val} onChange={(e) => setVal(e.target.value)} placeholder="Your answer" />}
      <div className="row">
        <button className="primary" disabled={!has} onClick={() => setStage("save")}>Continue</button>
        {q.can_skip && <button disabled={busy} onClick={() => send({ action: "skip" })}>Skip</button>}
      </div>{err && <p className="error">{err}</p>}
    </div>
  );
}

function Review({ s, reload }) {
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const items = (s.results || []).filter((i) => i.status !== "planned");
  const rv = s.review || {};
  const editable = (i) => i.step === s.step && !["file", "manual"].includes(i.kind) && i.status !== "manual";
  const approve = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/agent/sessions/${s.id}/approve`, { edits }); reload(); } catch (e) { setErr(e.message); setBusy(false); }
  };
  const cancel = async () => { await api.post(`/agent/sessions/${s.id}/cancel`); reload(); };
  const control = (i) => {
    const v = edits[i.sk] ?? (i.value ?? "");
    const on = (x) => setEdits({ ...edits, [i.sk]: x });
    if (i.kind === "checkbox") return <select value={v} onChange={(e) => on(e.target.value)}><option>Checked</option><option>Unchecked</option></select>;
    if (i.options?.length && i.kind !== "checkbox_group") return <select value={v} onChange={(e) => on(e.target.value)}><option value="">(none)</option>{i.options.map((o) => <option key={o.id}>{o.label}</option>)}</select>;
    if (i.kind === "textarea" || String(v).length > 80) return <textarea rows={Math.min(10, Math.max(3, Math.ceil(String(v).length / 80)))} value={v} onChange={(e) => on(e.target.value)} />;
    return <input value={v} onChange={(e) => on(e.target.value)} />;
  };
  return (
    <section className="review">
      <h2>Review before anything is sent</h2>
      <p className="muted">Nothing has been submitted. Check every answer, edit anything that’s off, then approve. The browser window shows the live form.</p>
      {rv.missing?.length > 0 && <p className="notice bad">Required fields still empty: {rv.missing.join(", ")}. Fill them in the browser window before approving.</p>}
      {(rv.warnings || []).map((w) => <p key={w} className="notice warn">{w}</p>)}
      <table className="fields review-t"><tbody>
        {items.map((i) => (
          <tr key={i.sk} className={i.flags?.some((f) => ["ai_generated", "sensitive", "verify_failed"].includes(f)) ? "hot" : ""}>
            <td className="lbl">{i.label}</td>
            <td className="val">{editable(i) ? control(i) : (i.value ?? <span className="muted">{i.note || "Left blank"}</span>)}</td>
            <td className="tags"><SourceChip source={i.source} /><FlagChips flags={i.flags} />{i.status === "skipped" && <Chip>Skipped</Chip>}</td>
          </tr>))}
      </tbody></table>
      {err && <p className="error">{err}</p>}
      <div className="row">
        <button className="primary" disabled={busy} onClick={approve}>Approve and submit</button>
        <button className="danger" onClick={cancel}>Cancel application</button>
      </div>
      <Snapshot id={s.id} />
    </section>
  );
}

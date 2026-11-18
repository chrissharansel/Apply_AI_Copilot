import { useEffect, useState } from "react";
import { api } from "../api";
import { Chip, when } from "../ui.jsx";

export default function Knowledge() {
  const [rows, setRows] = useState([]);
  const [cats, setCats] = useState([]);
  const [cat, setCat] = useState("");
  const [only, setOnly] = useState(false);
  const [edit, setEdit] = useState(null);
  const [nw, setNw] = useState({ question: "", answer: "" });
  const [err, setErr] = useState("");
  const load = () => api.get(`/knowledge?needs_confirmation=${only}${cat ? `&category=${cat}` : ""}`).then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { api.get("/knowledge/categories").then(setCats).catch(() => {}); }, []);
  useEffect(() => { load(); }, [cat, only]); // eslint-disable-line
  const run = async (fn) => { setErr(""); try { await fn(); await load(); } catch (e) { setErr(e.message); } };
  const add = (e) => { e.preventDefault(); run(async () => { await api.post("/knowledge", nw); setNw({ question: "", answer: "" }); }); };
  return (
    <div className="page">
      <h1>Saved answers</h1>
      <p className="muted">Answers you’ve confirmed are reused automatically. Sensitive answers are only reused on an exact question match, and anything old or unconfirmed gets double-checked with you first.</p>
      <form className="row wrap addbar" onSubmit={add}>
        <input placeholder="Question, e.g. Are you willing to relocate?" value={nw.question} onChange={(e) => setNw({ ...nw, question: e.target.value })} required minLength={3} />
        <input placeholder="Your answer" value={nw.answer} onChange={(e) => setNw({ ...nw, answer: e.target.value })} required />
        <button className="primary">Add</button>
      </form>
      <div className="row">
        <select value={cat} onChange={(e) => setCat(e.target.value)}><option value="">All categories</option>{cats.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}</select>
        <label className="inline"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} /> Only needs confirmation</label>
      </div>
      {err && <p className="error">{err}</p>}
      {rows.length === 0 ? <p className="muted">No saved answers yet. They appear when you answer the agent’s questions and choose to save.</p> : (
        <table><thead><tr><th>Question</th><th>Answer</th><th>Status</th><th>Reuse</th><th></th></tr></thead><tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.question}<div className="muted small">{r.category.replace(/_/g, " ")}, updated {when(r.updated_at)}</div></td>
              <td>{edit?.id === r.id ? <input autoFocus value={edit.answer} onChange={(e) => setEdit({ ...edit, answer: e.target.value })} /> : r.answer}</td>
              <td>{r.needs_confirmation ? <Chip cls="c-amber">{r.verified ? "Old, reconfirm" : "Unconfirmed"}</Chip> : <Chip cls="c-green">Confirmed</Chip>}{r.sensitive && <Chip cls="c-rose">Sensitive</Chip>}{r.application_id && <Chip>One job only</Chip>}</td>
              <td><label className="inline"><input type="checkbox" checked={r.reusable} onChange={(e) => run(() => api.put(`/knowledge/${r.id}`, { reusable: e.target.checked }))} /> Reuse</label></td>
              <td className="acts">
                {edit?.id === r.id ? <><button className="link" onClick={() => run(async () => { await api.put(`/knowledge/${r.id}`, { answer: edit.answer }); setEdit(null); })}>Save</button><button className="link" onClick={() => setEdit(null)}>Cancel</button></>
                  : <><button className="link" onClick={() => setEdit({ id: r.id, answer: r.answer })}>Edit</button>
                    {r.needs_confirmation && <button className="link" onClick={() => run(() => api.post(`/knowledge/${r.id}/confirm`))}>Still correct</button>}
                    <button className="link danger-t" onClick={() => run(() => api.del(`/knowledge/${r.id}`))}>Delete</button></>}
              </td>
            </tr>))}
        </tbody></table>)}
    </div>
  );
}

import { useState } from "react";
import { api } from "../../api";
import { Chip } from "../../ui.jsx";

const ST = { confirmed: ["Confirmed", "c-green"], stale: ["Reconfirm (old)", "c-amber"], needs_confirmation: ["Needs confirmation", "c-amber"], missing: ["Missing", "c-grey"] };
const SRC = { user_confirmed: "c-green", approved: "c-green", calculated: "c-blue", user_entered: "c-amber", resume_link: "c-amber", resume: "c-amber", unverified: "c-amber", missing: "c-grey" };

export default function Facts({ p, setP, flash, fail }) {
  const [f, setF] = useState("all");
  const rows = p.facts.filter((r) => f === "all" || (f === "todo" ? ["needs_confirmation", "stale"].includes(r.status) : r.status === f));
  const confirmAll = async () => { try { setP(await api.put("/profile", { data: p.data, confirm: true })); flash("Everything is confirmed."); } catch (e) { fail(e); } };
  return (
    <div>
      <p className="muted">Every detail has a source and a confidence. The agent types in only <b>confirmed</b> facts. Anything read from a resume, typed but not confirmed, or missing becomes a question or a suggestion instead, so forms never get invented or unreliable details.</p>
      <div className="row wrap">{[["all", "All"], ["todo", "Needs confirmation"], ["missing", "Missing"], ["confirmed", "Confirmed"]].map(([k, l]) => <button key={k} className={f === k ? "on" : ""} onClick={() => setF(k)}>{l}</button>)}
        <button className="primary" onClick={confirmAll} title="Marks every value on your profile as correct">Confirm everything as correct</button></div>
      <table><thead><tr><th>Fact</th><th>Value</th><th>Source</th><th>Confidence</th><th>Status</th></tr></thead><tbody>
        {rows.map((r) => <tr key={r.path}><td>{r.label}{r.core && r.status === "missing" && <span className="req"> needed</span>}</td><td className="small">{r.value || <span className="muted">(none)</span>}</td>
          <td><Chip cls={SRC[r.source]}>{r.source_label}</Chip></td><td><span className="conf"><i style={{ width: `${r.confidence * 100}%` }} /></span> <span className="small">{Math.round(r.confidence * 100)}%</span></td>
          <td><Chip cls={ST[r.status][1]}>{ST[r.status][0]}</Chip></td></tr>)}
      </tbody></table>
    </div>
  );
}

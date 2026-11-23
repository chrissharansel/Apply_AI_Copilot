import { useEffect, useState } from "react";
import { api } from "../api";
import { Chip, when } from "../ui.jsx";
import Resumes from "./profile/Resumes.jsx";
import Details from "./profile/Details.jsx";
import Experience from "./profile/Experience.jsx";
import Conflicts from "./profile/Conflicts.jsx";
import Facts from "./profile/Facts.jsx";

const TABS = [["resumes", "Resumes"], ["details", "Details"], ["experience", "Experience"], ["conflicts", "Conflicts"], ["facts", "Confidence"]];

export default function Profile() {
  const [p, setP] = useState(null);
  const [tab, setTab] = useState("resumes");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [nConf, setNConf] = useState(0);
  const reload = async () => {
    setP(await api.get("/profile"));
    try { const c = await api.get("/profile/conflicts"); setNConf(c.conflicts.filter((x) => x.kind !== "missing_in_resume").length); } catch { setNConf(0); }
  };
  useEffect(() => { reload().catch((e) => setErr(e.message)); }, []);
  if (!p) return <div className="page"><p className="muted">{err || "Loading…"}</p></div>;
  const common = { p, setP, reload, goto: setTab, flash: (m) => { setMsg(m); setErr(""); }, fail: (e) => { setErr(e.message || String(e)); setMsg(""); } };
  const s = p.summary || {};
  return (
    <div className="page narrow">
      <div className="row between"><h1>Profile</h1>
        <div className="row">{p.confirmed ? <Chip cls="c-green">Reviewed {when(p.confirmed_at)}</Chip> : <Chip cls="c-amber">Not reviewed yet</Chip>}</div></div>
      <p className="muted small">{s.confirmed || 0} confirmed facts, {s.needs_confirmation || 0} waiting for your confirmation, {s.missing || 0} missing. The agent only types in confirmed facts; everything else is offered to you as a suggestion.</p>
      <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}{k === "conflicts" && nConf > 0 && <span className="badge">{nConf}</span>}</button>)}</div>
      {msg && <p className="notice good">{msg}</p>}{err && <p className="error">{err}</p>}
      {tab === "resumes" && <Resumes {...common} />}
      {tab === "details" && <Details {...common} />}
      {tab === "experience" && <Experience {...common} />}
      {tab === "conflicts" && <Conflicts {...common} onChange={reload} />}
      {tab === "facts" && <Facts {...common} />}
    </div>
  );
}

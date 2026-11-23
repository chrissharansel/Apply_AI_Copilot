import { useEffect, useState } from "react";
import { api } from "../api";
import { Chip, Field } from "../ui.jsx";

export default function Developer() {
  const [catalog, setCatalog] = useState({ agents: [], tools: [] });
  const [task, setTask] = useState("Inspect the available agents, tools and workflow capabilities.");
  const [role, setRole] = useState("developer");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get("/agent/workbench/catalog").then(setCatalog).catch((e) => setError(e.message)); }, []);

  const run = async (e) => {
    e.preventDefault(); setBusy(true); setError(""); setResult(null);
    try {
      const r = await api.post("/agent/workbench/run", {
        role, task,
        context: { title, description }
      });
      setResult(r);
    } catch (e2) { setError(e2.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="page">
      <div className="studio-hero">
        <div><div className="eyebrow">AGENT ENGINEERING WORKSPACE</div><h1>Developer Studio</h1>
          <p className="muted">Inspect agent capabilities, registered tools, schemas and nested tool-call traces. This workspace is read-only for production candidate data.</p></div>
        <Chip cls="c-blue">Orchestrator v2</Chip>
      </div>

      <div className="studio-grid">
        <section className="studio-panel">
          <div className="section-heading"><div><h2>Agent registry</h2><p className="muted small">Agents are selected by role and task context.</p></div><Chip>{catalog.agents.length} agents</Chip></div>
          <div className="agent-cards">{catalog.agents.map((a) => <article className="agent-card" key={a.id}>
            <div className="row between"><h3>{a.name}</h3><Chip cls={a.role === "developer" ? "c-blue" : "c-green"}>{a.role}</Chip></div>
            <p className="muted small">{a.description}</p>
            <div className="tag-wrap">{a.capabilities.map((c) => <Chip key={c}>{c.replaceAll("_", " ")}</Chip>)}</div>
            <p className="small"><b>Allowed tools:</b> {a.tools.length}</p>
          </article>)}</div>
        </section>

        <section className="studio-panel">
          <div className="section-heading"><div><h2>Registered tools</h2><p className="muted small">Tools have schemas and are invoked through the runtime registry.</p></div><Chip>{catalog.tools.length} tools</Chip></div>
          <div className="tool-list">{catalog.tools.map((t) => <details className="tool-item" key={t.id}>
            <summary><span><b>{t.name}</b><small>{t.id}</small></span><Chip>{t.tags[0] || "tool"}</Chip></summary>
            <p className="muted small">{t.description}</p>
            <pre>{JSON.stringify(t.input_schema, null, 2)}</pre>
          </details>)}</div>
        </section>
      </div>

      <section className="studio-panel run-panel">
        <div className="section-heading"><div><h2>Run a workflow</h2><p className="muted small">The router selects a specialist agent, then a planner selects registered tools. The runtime validates each tool ID and records nested calls.</p></div><Chip cls="c-amber">Sandboxed tool execution</Chip></div>
        <form onSubmit={run}>
          <div className="grid2">
            <Field label="Select execution workspace"><select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="developer">Developer agent registry</option><option value="applicant">Applicant agent team</option>
            </select></Field>
            <Field label="Task"><textarea rows={2} value={task} onChange={(e) => setTask(e.target.value)} /></Field>
          </div>
          <div className="grid2">
            <Field label="Optional job title"><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Python Developer" /></Field>
            <Field label="Optional job description"><textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Paste role requirements to test the applicant workflow" /></Field>
          </div>
          <div className="row between"><span className="muted small">No browser actions or application submissions are exposed in Developer Studio.</span><button className="primary" disabled={busy}>{busy ? "Running tools…" : "Run workflow"}</button></div>
        </form>
        {error && <p className="notice bad">{error}</p>}
        {result && <div className="run-results">
          <h3>Execution result · {result.agent?.name}</h3>
          <div className="trace-list">{(result.trace || []).map((t, i) => <div className="trace-row" key={`${t.tool}-${i}`}>
            <span className="trace-index">{i + 1}</span><div style={{ paddingLeft: `${(t.depth || 0) * 14}px` }}><b>{t.name || t.tool}</b><small>{t.tool}</small>{t.error && <p className="error">{t.error}</p>}</div>
            <Chip cls={t.status === "success" ? "c-green" : t.status === "error" ? "c-red" : "c-grey"}>{t.status}</Chip>
          </div>)}</div>
          <pre className="result-json">{JSON.stringify(result.results, null, 2)}</pre>
        </div>}
      </section>
    </div>
  );
}

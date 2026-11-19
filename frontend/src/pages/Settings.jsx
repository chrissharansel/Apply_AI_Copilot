import { useEffect, useState } from "react";
import { api } from "../api";
import { Field } from "../ui.jsx";

export default function Settings() {
  const [s, setS] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api.get("/settings").then(setS).catch((e) => setErr(e.message)); }, []);
  if (!s) return <div className="page"><p className="muted">{err || "Loading…"}</p></div>;
  const set = (k, v) => { setS({ ...s, [k]: v }); setMsg(""); };
  const save = async () => { setErr(""); try { setS(await api.put("/settings", s)); setMsg("Saved. New applications use these settings."); } catch (e) { setErr(e.message); } };
  return (
    <div className="page narrow">
      <h1>Settings</h1>
      <p className="muted">How much the agent does on its own, and how it writes for you. You can override the first two per application on the Apply page.</p>

      <h2>Writing</h2>
      <Field label="Free-text questions (“Why do you want this job?”, cover letters)">
        <select value={s.ai_answers} onChange={(e) => set("ai_answers", e.target.value)}>
          <option value="auto">AI drafts them, I review before submitting</option>
          <option value="ask">I write them (I can ask the AI for a draft on each question)</option>
        </select></Field>
      <div className="grid2">
        <Field label="Tone"><select value={s.tone} onChange={(e) => set("tone", e.target.value)}>
          <option value="professional">Professional</option><option value="friendly">Friendly</option><option value="concise">Concise</option><option value="confident">Confident</option></select></Field>
        <Field label={`Target length: about ${s.max_words} words`}><input type="range" min="40" max="400" step="10" value={s.max_words} onChange={(e) => set("max_words", +e.target.value)} /></Field>
      </div>
      <Field label="Standing instructions for the AI (optional)">
        <textarea rows={3} value={s.writing_notes} onChange={(e) => set("writing_notes", e.target.value)} placeholder="e.g. Avoid buzzwords. Mention that I enjoy mentoring. Keep it in British English." /></Field>
      <p className="muted small">The AI only uses facts from your confirmed profile and saved answers. These instructions change style and emphasis, never the facts.</p>

      <h2>Autopilot</h2>
      <label className="inline"><input type="checkbox" checked={s.auto_advance} onChange={(e) => set("auto_advance", e.target.checked)} /> Move to the next page automatically</label>
      <p className="muted small">Turn this off for step-by-step mode: the agent fills a page, then waits for you to look it over before continuing.</p>
      <label className="inline"><input type="checkbox" checked={s.semantic_reuse} onChange={(e) => set("semantic_reuse", e.target.checked)} /> Reuse saved answers for similarly worded questions</label>
      <p className="muted small">Off = only identical questions are answered automatically; similar ones are offered to you as suggestions. Sensitive questions are always exact-match only.</p>
      <label className="inline"><input type="checkbox" checked={s.show_browser} onChange={(e) => set("show_browser", e.target.checked)} /> Show the browser window</label>
      <p className="muted small">Keep this on unless you’re sure no CAPTCHA or login will appear.</p>

      {msg && <p className="notice good">{msg}</p>}{err && <p className="error">{err}</p>}
      <div className="row sticky"><button className="primary" onClick={save}>Save settings</button></div>
    </div>
  );
}

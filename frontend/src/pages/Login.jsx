import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api";
import { Field } from "../ui.jsx";

export default function Login() {
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const r = await api.post(mode === "login" ? "/auth/login" : "/auth/register", mode === "login" ? { email: f.email, password: f.password } : f);
      auth.set(r.token); nav(mode === "login" ? "/" : "/profile");
    } catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };
  return (
    <div className="login">
      <div className="login-copy">
        <h1>Paste a job link.<br />Your agent does the form.</h1>
        <p>It reads your confirmed profile, reuses answers you’ve already given, and asks you only about what it doesn’t know. Nothing is submitted without your approval.</p>
      </div>
      <form onSubmit={submit} className="login-form">
        <h2>{mode === "login" ? "Sign in" : "Create your account"}</h2>
        {mode === "register" && <Field label="Name"><input value={f.name} onChange={set("name")} required /></Field>}
        <Field label="Email"><input type="email" value={f.email} onChange={set("email")} required /></Field>
        <Field label="Password"><input type="password" value={f.password} onChange={set("password")} minLength={8} required /></Field>
        {err && <p className="error">{err}</p>}
        <button className="primary" disabled={busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}

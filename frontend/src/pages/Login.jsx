import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useAuth } from "../lib/auth.jsx";

export default function Login() {
  const { login, signup } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [mode, setMode] = useState(params.get("mode") === "signup" ? "signup" : "login");
  const [form, setForm] = useState({ email: "", password: "", display_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = params.get("next");
  const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/transactions";

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await (mode === "login" ? login({ email: form.email, password: form.password }) : signup(form));
      navigate(safeNext, { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <div className="narrow">
      <h1 className="page-title">{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <p className="lede">
        An account keeps your transaction history, cases and reports so patterns across payments can be detected.
        This is a UPI Guard password, <b>never your bank or UPI PIN</b>.
      </p>
      <form className="card-form" onSubmit={submit} noValidate>
        {mode === "signup" && (
          <div className="field">
            <label htmlFor="display_name">Name <span className="hint">(optional)</span></label>
            <input id="display_name" type="text" autoComplete="nickname" value={form.display_name} onChange={set("display_name")} maxLength={80} />
          </div>
        )}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="text" inputMode="email" autoComplete="email" value={form.email} onChange={set("email")} required />
        </div>
        <div className="field">
          <label htmlFor="password">Password {mode === "signup" && <span className="hint">(at least 10 characters)</span>}</label>
          <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"}
                 value={form.password} onChange={set("password")} required minLength={mode === "signup" ? 10 : 1} />
        </div>
        <button className="primary" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
        <div className="error" role="alert">{error}</div>
      </form>
      <p>
        {mode === "login" ? "New here? " : "Already have an account? "}
        <button type="button" className="textbtn" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}>
          {mode === "login" ? "Create an account" : "Sign in"}
        </button>
      </p>
      <p className="note">You can use the checker, scanners and simulator without an account. <Link to="/check">Check a payment →</Link></p>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router";
import { aiAsk, aiStatus } from "../lib/api.js";

/** AI investigator: explains stored evidence with citations. Off unless the user opted in. */
export default function AiPanel({ transactionId, caseId, suggestions }) {
  const [status, setStatus] = useState(null);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { aiStatus().then(setStatus).catch(() => setStatus({ configured: false })); }, []);

  async function ask(q) {
    const text = (q ?? question).trim();
    if (text.length < 2) return;
    setBusy(true);
    setError("");
    try {
      const history = turns.flatMap((t) => [{ role: "user", text: t.q }, { role: "assistant", text: t.a.answer }]).slice(-6);
      const a = await aiAsk({ question: text, consent: true, transaction_id: transactionId ?? null, case_id: caseId ?? null, history });
      setTurns([...turns, { q: text, a }]);
      setQuestion("");
      setStatus((s) => s && { ...s, used_today: s.used_today + 1 });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel ai-panel" aria-labelledby="ai-title">
      <h2 className="panel-title" id="ai-title">AI investigator</h2>
      {!status ? <p className="muted">Checking…</p> : !status.configured ? (
        <p className="muted">The AI investigator isn't set up on this server. Everything else works without it.</p>
      ) : !status.consent ? (
        <p className="muted">
          Off. When you turn it on, your question and the transactions it needs are sent to Anthropic's Claude API to
          write an explanation. <Link to="/settings#ai">Turn on in Settings →</Link>
        </p>
      ) : (
        <>
          <p className="note">Explains the evidence UPI Guard already found, citing your transactions. It can't see other
            users' data and doesn't decide if something is fraud. {status.used_today}/{status.daily_limit} questions today.</p>
          {turns.map((t, i) => <Answer key={i} q={t.q} a={t.a} />)}
          {turns.length === 0 && suggestions?.length > 0 && (
            <div className="chips-row">
              {suggestions.map((s) => <button key={s} type="button" className="chip-btn" disabled={busy} onClick={() => ask(s)}>{s}</button>)}
            </div>
          )}
          <form className="ai-form" onSubmit={(e) => { e.preventDefault(); ask(); }}>
            <label htmlFor="aiq" className="sr-only">Question</label>
            <input id="aiq" type="text" maxLength={1000} placeholder="Ask about this evidence…" value={question}
                   onChange={(e) => setQuestion(e.target.value)} disabled={busy} />
            <button type="submit" className="primary small" disabled={busy || question.trim().length < 2}>{busy ? "Thinking…" : "Ask"}</button>
          </form>
          <div className="error" role="alert">{error}</div>
        </>
      )}
    </section>
  );
}

function Answer({ q, a }) {
  return (
    <div className="ai-turn" aria-live="polite">
      <p className="ai-q">{q}</p>
      <div className="ai-a">{a.answer.split("\n").map((line, i) => <p key={i}>{linkify(line)}</p>)}</div>
      {a.evidence.length > 0 && (
        <p className="ai-evidence"><span className="label">Evidence used</span>{" "}
          {a.evidence.map((e) => e.type === "tx"
            ? <Link key={"t" + e.id} to={`/investigate/${e.id}`}>tx#{e.id}</Link>
            : <Link key={"c" + e.id} to={`/cases/${e.id}`}>case#{e.id}</Link>)}
        </p>
      )}
      {a.unverified.length > 0 && <p className="warn-note">Removed references not found in your data: {a.unverified.join(", ")}.</p>}
      {a.tool_calls.length > 0 && (
        <details className="tool-calls"><summary>{a.tool_calls.length} lookup{a.tool_calls.length > 1 ? "s" : ""} · {a.model}</summary>
          <ul>{a.tool_calls.map((c, i) => <li key={i}><code>{c.tool}</code> {JSON.stringify(c.input)}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

/** Turn [tx#12] / [case#3] citations into links. */
function linkify(line) {
  const parts = line.split(/(\[(?:tx|case)#\d+\])/g);
  return parts.map((p, i) => {
    const m = p.match(/^\[(tx|case)#(\d+)\]$/);
    if (!m) return p;
    return <Link key={i} className="cite" to={m[1] === "tx" ? `/investigate/${m[2]}` : `/cases/${m[2]}`}>{m[1]}#{m[2]}</Link>;
  });
}

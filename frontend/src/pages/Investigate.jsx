import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import AiPanel from "../components/AiPanel.jsx";
import Verdict from "../components/Verdict.jsx";
import { Breakdown, ErrorNote, Level, Loading, Reasons, Section, Synthetic, TxRow } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { DIRECTION, inr, party, when } from "../lib/format.js";

const REVIEW = [["legitimate", "This is fine"], ["suspicious", "Looks suspicious"], ["confirmed_fraud", "It was fraud"]];

export default function Investigate() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [note, setNote] = useState("");
  const [cases, setCases] = useState([]);
  const [msg, setMsg] = useState("");
  const [bal, setBal] = useState("");
  const [balError, setBalError] = useState("");

  const load = useCallback(() => {
    setError(null);
    api.getInvestigation(id).then(setData).catch(setError);
  }, [id]);
  useEffect(() => { setData(null); load(); api.listCases().then(setCases).catch(() => {}); }, [load]);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading text="Loading investigation…" />;

  const t = data.transaction;
  const risk = t.risk || {};
  const comps = risk.components || {};
  const cp = data.counterparty;

  async function review(status) {
    const updated = await api.reviewTransaction(t.id, status);
    setData({ ...data, transaction: { ...t, review_status: updated.review_status } });
  }
  async function addBalance(e) {
    e.preventDefault();
    setBalError("");
    try {
      await api.updateTransaction(t.id, { balance_before: Number(bal) });
      setBal("");
      load();
    } catch (err) {
      setBalError(err.message);
    }
  }
  async function addNote(e) {
    e.preventDefault();
    if (!note.trim()) return;
    await api.addTxNote(t.id, note.trim());
    setNote("");
    load();
  }
  async function openCase() {
    const c = await api.createCase({ title: `${inr(t.amount)} ${t.direction === "received" ? "from" : "to"} ${party(t)}`,
                                     priority: t.risk_level === "high" ? "high" : "medium", transaction_ids: [t.id] });
    navigate(`/cases/${c.id}`);
  }
  async function addToCase(caseId) {
    await api.linkCaseTx(caseId, t.id);
    setMsg("Added to the case.");
    load();
  }
  async function remove() {
    if (!confirm("Delete this transaction from your history?")) return;
    await api.deleteTransaction(t.id);
    navigate("/transactions");
  }

  return (
    <div className="investigate">
      <p className="crumbs"><Link to="/transactions">← My payments</Link></p>
      <header className="inv-head simple">
        <p className="label">{t.direction === "received" ? "Received" : t.direction === "cash_out" ? "Cash withdrawal" : "Paid"} · {when(t.occurred_at)} {t.is_synthetic && <Synthetic small />}</p>
        <h1 className="inv-amount">{inr(t.amount)}</h1>
        <p className="inv-party">{t.direction === "received" ? "from" : "to"} <b>{party(t)}</b>
          {t.counterparty_name && t.counterparty_upi && <> · {t.counterparty_name}</>}
          {t.payment_app && <> · {t.payment_app}</>}{t.external_id && <> · Ref {t.external_id}</>}</p>
      </header>

      <Verdict kind={t.direction === "received" ? "received" : "sent"} level={t.risk_level || "unknown"}
               reasons={(risk.reasons || []).filter((r) => r.direction !== "down")} />

      {comps.model && !comps.model.available && t.direction !== "received" && (
        <form className="add-balance" onSubmit={addBalance}>
          <label htmlFor="bal">For a full check, add your bank balance before this payment <span className="hint">(it's in your bank SMS)</span></label>
          <div className="add-balance-row">
            <div className="money"><input id="bal" type="number" inputMode="decimal" min="0" step="0.01" value={bal} onChange={(e) => setBal(e.target.value)} /></div>
            <button type="submit" className="big-btn primary-btn" disabled={!bal}>Check again</button>
          </div>
          {balError && <p className="error-box" role="alert">{balError}</p>}
        </form>
      )}

      <div className="review-bar" role="group" aria-label="Mark this payment">
        <span className="verdict-sub">Mark this payment:</span>
        {REVIEW.map(([v, label]) => (
          <button key={v} type="button" className={"pill" + (t.review_status === v ? " on" : "")} aria-pressed={t.review_status === v}
                  onClick={() => review(t.review_status === v ? "unreviewed" : v)}>{label}</button>
        ))}
      </div>

      <details className="more-details full-details">
        <summary>Full details: score, evidence, timeline, notes</summary>
      <div className="inv-grid">
        <div>
          <Section no="01" title="Why this score">
            <Breakdown risk={risk} />
            {risk.notes?.length > 0 && <ul className="notes-list">{risk.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
          </Section>

          {comps.model?.available && (
            <Section no="02" title="ML model evidence" aside={<Level level={comps.model.level}>{(comps.model.probability * 100).toFixed(comps.model.probability < 0.01 ? 2 : 1)}%</Level>}>
              <p className="muted">LightGBM fraud probability, with the signals that pushed it up (▲) or down (▼) (TreeSHAP).</p>
              <Reasons items={comps.model.reasons} />
            </Section>
          )}
          {comps.rules?.available && (
            <Section no="02" title="Received-money rules" aside={<Level level={comps.rules.level} />}>
              <Reasons items={comps.rules.reasons} />
            </Section>
          )}

          <Section no="03" title="Patterns in your history">
            {comps.patterns?.items?.length ? (
              <ul className="patterns">
                {comps.patterns.items.map((p) => (
                  <li key={p.code}>
                    <Level level={p.severity}>{p.title}</Level>
                    <p>{p.detail}</p>
                    {p.informational && <p className="note">Shown for context; already counted by the model.</p>}
                  </li>
                ))}
              </ul>
            ) : <p className="muted">No unusual patterns compared with your history{risk.baseline?.history_count < 5 ? " (there isn't much history yet)" : ""}.</p>}
            {risk.baseline && (
              <dl className="lines baseline">
                <div><dt>Earlier transactions</dt><span className="leader" /><dd>{risk.baseline.history_count}</dd></div>
                {risk.baseline.median_amount != null && <div><dt>Your median payment</dt><span className="leader" /><dd>{inr(risk.baseline.median_amount)}</dd></div>}
                {risk.baseline.typical_range && <div><dt>Typical range</dt><span className="leader" /><dd>{inr(risk.baseline.typical_range[0])}–{inr(risk.baseline.typical_range[1])}</dd></div>}
                {risk.baseline.common_hours?.length > 0 && <div><dt>Usual hours</dt><span className="leader" /><dd>{risk.baseline.common_hours.map((h) => `${h}:00`).join(", ")}</dd></div>}
              </dl>
            )}
          </Section>

          <Section no="04" title="Timeline (24 hours either side)">
            <ol className="timeline">
              {data.timeline.map((x) => (
                <li key={x.id} className={x.id === t.id ? "current" : ""}>
                  <span className="tl-time">{when(x.occurred_at)}</span>
                  {x.id === t.id ? (
                    <span><b>This payment</b> · {inr(x.amount)} {x.direction === "received" ? "from" : "to"} {party(x)}</span>
                  ) : (
                    <Link to={`/investigate/${x.id}`}>{x.direction === "received" ? "+" : "−"}{inr(x.amount)} {party(x)}</Link>
                  )}
                  <Level level={x.risk_level}>{x.risk_score != null ? Math.round(x.risk_score * 100) : "–"}</Level>
                </li>
              ))}
            </ol>
          </Section>

          <Section no="05" title={`Other payments with ${party(t)}`}>
            {data.related.same_counterparty.length ? (
              <ul className="tx-list">{data.related.same_counterparty.slice(-10).reverse().map((x) => <TxRow key={x.id} t={x} compact />)}</ul>
            ) : <p className="muted">None. This is the first payment with this counterparty in your history.</p>}
          </Section>
        </div>

        <aside className="inv-side">
          <section className="panel">
            <h2 className="panel-title">Counterparty</h2>
            <dl className="lines">
              {cp.vpa && <div><dt>UPI ID</dt><span className="leader" /><dd>{cp.vpa}</dd></div>}
              {cp.app && <div><dt>App / bank</dt><span className="leader" /><dd>{cp.app}{cp.bank ? ` · ${cp.bank}` : ""}</dd></div>}
              <div><dt>Your payments</dt><span className="leader" /><dd>{cp.transactions}</dd></div>
              <div><dt>Total sent</dt><span className="leader" /><dd>{inr(cp.total_sent)}</dd></div>
              <div><dt>Total received</dt><span className="leader" /><dd>{inr(cp.total_received)}</dd></div>
              <div><dt>First seen</dt><span className="leader" /><dd>{when(cp.first_seen)}</dd></div>
              <div><dt>Community reports</dt><span className="leader" /><dd>{cp.community_reports} <small>(unverified)</small></dd></div>
            </dl>
            {cp.signals?.filter((s) => s.severity !== "info").map((s) => <p key={s.code} className="warn-note">{s.text}</p>)}
            <p className="panel-links">
              {cp.vpa && <Link to={`/before-you-pay?tab=upi&vpa=${encodeURIComponent(cp.vpa)}`}>Check UPI ID</Link>}
              <Link to={`/network?focus=${encodeURIComponent("party:" + (t.counterparty_upi || t.counterparty_name || "").toLowerCase())}`}>View in network</Link>
              {cp.vpa && <Link to={`/reports?vpa=${encodeURIComponent(cp.vpa)}`}>Report this UPI ID</Link>}
            </p>
          </section>

          <section className="panel">
            <h2 className="panel-title">Case</h2>
            {data.cases.length > 0 && (
              <ul className="plain">{data.cases.map((c) => <li key={c.id}><Link to={`/cases/${c.id}`}>{c.title}</Link> · {c.status}</li>)}</ul>
            )}
            <button type="button" className="primary small" onClick={openCase}>Open a new case</button>
            {cases.filter((c) => !data.cases.some((x) => x.id === c.id)).length > 0 && (
              <div className="field">
                <label htmlFor="addcase">Or add to an existing case</label>
                <select id="addcase" defaultValue="" onChange={(e) => e.target.value && addToCase(Number(e.target.value))}>
                  <option value="">Choose a case…</option>
                  {cases.filter((c) => !data.cases.some((x) => x.id === c.id)).map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
                </select>
              </div>
            )}
            {msg && <p className="note" role="status">{msg}</p>}
          </section>

          <AiPanel transactionId={t.id} suggestions={["Why was this flagged?", "What happened before this payment?",
            "Is this consistent with account takeover?", "Show all payments to this UPI ID"]} />

          <section className="panel">
            <h2 className="panel-title">Notes</h2>
            {data.notes.length ? <ul className="notes">{data.notes.map((n) => <li key={n.id}><span className="note">{when(n.created_at)}</span><p>{n.text}</p></li>)}</ul>
              : <p className="muted">No notes yet.</p>}
            <form onSubmit={addNote}>
              <label htmlFor="note" className="sr-only">Add a note</label>
              <textarea id="note" rows={3} maxLength={2000} placeholder="e.g. Called the bank, complaint no. …" value={note} onChange={(e) => setNote(e.target.value)} />
              <button type="submit" className="ghost small" disabled={!note.trim()}>Add note</button>
            </form>
            <p className="note">Don't paste OTPs or PINs; anything that looks like one is masked in case evidence.</p>
          </section>

          <button type="button" className="textbtn danger" onClick={remove}>Delete this transaction</button>
        </aside>
      </div>
      </details>
    </div>
  );
}

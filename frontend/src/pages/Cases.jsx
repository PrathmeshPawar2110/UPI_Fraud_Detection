import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import AiPanel from "../components/AiPanel.jsx";
import { Empty, ErrorNote, Level, Loading, PageHead, Section, TxRow } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { downloadJson, inr, when } from "../lib/format.js";

const STATUSES = ["OPEN", "INVESTIGATING", "ESCALATED", "RESOLVED", "FALSE_POSITIVE"];
const STATUS_TEXT = { OPEN: "Open", INVESTIGATING: "Investigating", ESCALATED: "Escalated", RESOLVED: "Resolved", FALSE_POSITIVE: "False positive" };
const EVIDENCE_TYPES = [["message", "Message (SMS / WhatsApp)", "text"], ["url", "Link", "url"], ["upi", "UPI ID", "upi"],
                        ["qr", "QR payload", "payload"], ["screenshot", "Screenshot details", "text"], ["note", "Other", "text"]];

export function CaseList() {
  const [cases, setCases] = useState(null);
  const [error, setError] = useState(null);
  const [title, setTitle] = useState("");
  const navigate = useNavigate();
  useEffect(() => { api.listCases().then(setCases).catch(setError); }, []);

  async function create(e) {
    e.preventDefault();
    try {
      const c = await api.createCase({ title: title.trim() });
      navigate(`/cases/${c.id}`);
    } catch (err) { setError(err); }
  }

  return (
    <>
      <PageHead kicker="Cases" title="Fraud cases">
        Group related transactions, messages, links and notes into a case, track its status, and generate an incident
        report for your bank or the cyber-crime portal.
      </PageHead>
      <form className="inline-form" onSubmit={create}>
        <label htmlFor="ctitle" className="sr-only">New case title</label>
        <input id="ctitle" type="text" minLength={3} maxLength={140} placeholder="New case, e.g. 'Fake KYC call on 3 Oct'" value={title} onChange={(e) => setTitle(e.target.value)} />
        <button type="submit" className="primary small" disabled={title.trim().length < 3}>Create case</button>
      </form>
      <ErrorNote error={error} />
      {!cases ? <Loading /> : cases.length === 0 ? (
        <Empty title="No cases yet.">Open one from any transaction's investigation page, or create one above.</Empty>
      ) : (
        <ul className="case-list">
          {cases.map((c) => (
            <li key={c.id}>
              <Link to={`/cases/${c.id}`}>
                <span className="case-title">{c.title}</span>
                <span className="case-meta">{STATUS_TEXT[c.status]} · {c.priority} priority · {c.transaction_count} transaction{c.transaction_count === 1 ? "" : "s"} · updated {when(c.updated_at)}</span>
                {c.max_risk && <Level level={c.max_risk} />}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function CaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [c, setC] = useState(null);
  const [error, setError] = useState(null);
  const [note, setNote] = useState("");
  const [ev, setEv] = useState({ type: "message", label: "", value: "" });

  const load = useCallback(() => api.getCase(id).then(setC).catch(setError), [id]);
  useEffect(() => { load(); }, [load]);

  if (error) return <ErrorNote error={error} />;
  if (!c) return <Loading />;

  const update = async (body) => setC(await api.updateCase(c.id, body));
  async function addNote(e) {
    e.preventDefault();
    setC(await api.addCaseNote(c.id, note.trim()));
    setNote("");
  }
  async function addEvidence(e) {
    e.preventDefault();
    const key = EVIDENCE_TYPES.find(([t]) => t === ev.type)[2];
    try {
      setC(await api.addCaseEvidence(c.id, { type: ev.type, label: ev.label.trim() || ev.type, data: { [key]: ev.value.trim() } }));
      setEv({ ...ev, label: "", value: "" });
    } catch (err) { setError(err); }
  }
  async function remove() {
    if (!confirm("Delete this case? Its transactions stay in your history.")) return;
    await api.deleteCase(c.id);
    navigate("/cases");
  }

  return (
    <div className="case-detail">
      <p className="crumbs"><Link to="/cases">Cases</Link> / #{c.id}</p>
      <PageHead kicker={`Case #${c.id} · created ${when(c.created_at)}`} title={c.title}
        actions={<Link className="button primary-link" to={`/cases/${c.id}/report`}>Incident report</Link>} />

      <div className="case-controls">
        <div className="field">
          <label htmlFor="status">Status</label>
          <select id="status" value={c.status} onChange={(e) => update({ status: e.target.value })}>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_TEXT[s]}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="priority">Priority</label>
          <select id="priority" value={c.priority} onChange={(e) => update({ priority: e.target.value })}>
            {["low", "medium", "high"].map((p) => <option key={p}>{p}</option>)}
          </select>
        </div>
        {c.max_risk && <Level level={c.max_risk}>Highest risk: {c.max_risk}</Level>}
      </div>

      <div className="inv-grid">
        <div>
          <Section no="01" title="Transactions">
            {c.transactions.length ? <ul className="tx-list">{c.transactions.map((t) => <TxRow key={t.id} t={t} />)}</ul>
              : <p className="muted">None linked yet. Add one from its investigation page.</p>}
          </Section>

          <Section no="02" title="Evidence">
            {c.evidence.length ? (
              <ul className="evidence">
                {c.evidence.map((e, i) => (
                  <li key={i}><span className="label">{e.type}</span> <b>{e.label}</b> <span className="note">{when(e.added_at)}</span>
                    {Object.values(e.data || {}).filter(Boolean).map((v, j) => <p key={j} className="ev-data">{String(v)}</p>)}</li>
                ))}
              </ul>
            ) : <p className="muted">No evidence yet.</p>}
            <form className="evidence-form" onSubmit={addEvidence}>
              <div className="row">
                <div className="field">
                  <label htmlFor="evtype">Type</label>
                  <select id="evtype" value={ev.type} onChange={(e) => setEv({ ...ev, type: e.target.value })}>
                    {EVIDENCE_TYPES.map(([t, label]) => <option key={t} value={t}>{label}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="evlabel">Label</label>
                  <input id="evlabel" type="text" maxLength={140} placeholder="e.g. SMS from 'SBI-ALRT'" value={ev.label} onChange={(e) => setEv({ ...ev, label: e.target.value })} />
                </div>
              </div>
              <div className="field">
                <label htmlFor="evvalue">Content</label>
                <textarea id="evvalue" rows={3} maxLength={4000} value={ev.value} onChange={(e) => setEv({ ...ev, value: e.target.value })} />
              </div>
              <p className="note">Images aren't stored. OTPs, PINs and card numbers are masked automatically.</p>
              <button type="submit" className="ghost small" disabled={!ev.value.trim()}>Add evidence</button>
            </form>
          </Section>

          <Section no="03" title="Resolution">
            <form onSubmit={(e) => { e.preventDefault(); update({ resolution: e.target.resolution.value }); }}>
              <label htmlFor="resolution" className="sr-only">Resolution</label>
              <textarea id="resolution" name="resolution" rows={3} maxLength={4000} defaultValue={c.resolution || ""}
                        placeholder="Outcome, complaint numbers, refunds…" />
              <button type="submit" className="ghost small">Save</button>
            </form>
          </Section>
        </div>
        <aside className="inv-side">
          <AiPanel caseId={c.id} suggestions={["Summarize this case", "Which transaction is highest risk and why?", "Draft the timeline of events"]} />
          <section className="panel">
            <h2 className="panel-title">Notes</h2>
            {c.notes.length ? <ul className="notes">{c.notes.map((n) => <li key={n.id}><span className="note">{when(n.created_at)}</span><p>{n.text}</p></li>)}</ul>
              : <p className="muted">No notes yet.</p>}
            <form onSubmit={addNote}>
              <label htmlFor="cnote" className="sr-only">Add a note</label>
              <textarea id="cnote" rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
              <button type="submit" className="ghost small" disabled={!note.trim()}>Add note</button>
            </form>
          </section>
          <button type="button" className="textbtn danger" onClick={remove}>Delete case</button>
        </aside>
      </div>
    </div>
  );
}

export function CaseReport() {
  const { id } = useParams();
  const [r, setR] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.getCaseReport(id).then(setR).catch(setError); }, [id]);
  if (error) return <ErrorNote error={error} />;
  if (!r) return <Loading text="Building report…" />;

  return (
    <article className="report">
      <div className="report-actions no-print">
        <Link to={`/cases/${id}`}>← Back to case</Link>
        <button type="button" className="primary small" onClick={() => window.print()}>Print / save as PDF</button>
        <button type="button" className="ghost small" onClick={() => downloadJson(r, `upi-guard-case-${id}.json`)}>Download JSON</button>
      </div>
      <header>
        <p className="label">UPI Guard · generated {when(r.generated_at)}</p>
        <h1>{r.title}</h1>
        <p>Case #{r.case.id}: <b>{r.case.title}</b> · {r.case.status} · {r.case.priority} priority · opened {when(r.case.created_at)}</p>
        {r.summary.contains_synthetic_data && <p className="synthetic-note">Contains SYNTHETIC DEMO DATA, not real bank data.</p>}
      </header>

      <h2>Transaction summary</h2>
      <p>{r.summary.transactions} transaction(s) · sent {inr(r.summary.total_sent)} · received {inr(r.summary.total_received)}
        {r.summary.from && <> · {when(r.summary.from)} to {when(r.summary.to)}</>}</p>

      <h2>Risk assessment</h2>
      <p>Highest level: <Level level={r.risk_assessment.highest_level} /></p>
      <table className="report-table">
        <thead><tr><th>When</th><th>Direction</th><th>Amount</th><th>Counterparty</th><th>Ref</th><th>Score</th><th>Your review</th></tr></thead>
        <tbody>{r.risk_assessment.transactions.map((t) => (
          <tr key={t.id}><td>{when(t.occurred_at)}</td><td>{t.direction}</td><td>{inr(t.amount)}</td><td>{t.counterparty}</td>
            <td>{t.external_id || "–"}</td><td>{t.score} ({t.level})</td><td>{t.review_status.replace("_", " ")}</td></tr>))}</tbody>
      </table>

      {r.model_evidence.length > 0 && <><h2>Model evidence</h2>{r.model_evidence.map((m) => (
        <div key={m.transaction_id}><p className="label">Transaction #{m.transaction_id} · probability {(m.probability * 100).toFixed(1)}%</p>
          <ul>{m.reasons.map((x, i) => <li key={i}>{x.direction === "up" ? "▲" : "▼"} {x.text}</li>)}</ul></div>))}</>}
      {r.rule_evidence.length > 0 && <><h2>Rule evidence</h2>{r.rule_evidence.map((m) => (
        <div key={m.transaction_id}><p className="label">Transaction #{m.transaction_id} · {m.level}</p>
          <ul>{m.reasons.map((x, i) => <li key={i}>{x.text}</li>)}</ul></div>))}</>}
      {r.pattern_evidence.length > 0 && <><h2>Pattern evidence</h2>{r.pattern_evidence.map((m) => (
        <div key={m.transaction_id}><p className="label">Transaction #{m.transaction_id}</p>
          <ul>{m.patterns.map((p) => <li key={p.code}><b>{p.title}:</b> {p.detail}</li>)}</ul></div>))}</>}

      <h2>Timeline</h2>
      <ol className="report-timeline">{r.timeline.map((e, i) => <li key={i}><span className="tl-time">{when(e.at)}</span> [{e.kind}] {e.text}</li>)}</ol>

      <h2>Related entities</h2>
      {r.related_entities.length ? <ul>{r.related_entities.map((e) => (
        <li key={e.type + e.value}>{e.type.toUpperCase()}: {e.value}{e.name ? ` (${e.name})` : ""}{e.app ? ` · ${e.app}` : ""}
          {e.transactions ? ` · ${e.transactions} transaction(s)` : ""}{e.community_reports ? ` · ${e.community_reports} unverified report(s)` : ""}</li>))}</ul>
        : <p>None recorded.</p>}

      {r.evidence.length > 0 && <><h2>Evidence</h2><ul>{r.evidence.map((e, i) => (
        <li key={i}><b>{e.type}: {e.label}</b> ({when(e.added_at)}) {Object.values(e.data || {}).join(" · ")}</li>))}</ul></>}

      <h2>Investigation notes</h2>
      {r.notes.length ? <ul>{r.notes.map((n, i) => <li key={i}>{when(n.at)}: {n.text}</li>)}</ul> : <p>None.</p>}
      {r.case.resolution && <><h2>Resolution</h2><p>{r.case.resolution}</p></>}

      <h2>Recommended next steps</h2>
      <ol>{r.next_steps.map((s) => <li key={s}>{s}</li>)}</ol>
      <ul className="resources">{r.resources.map((x) => <li key={x.name}><b>{x.name}</b>: {x.contact}. {x.when}</li>)}</ul>
      <p className="disclaimer">{r.disclaimer}</p>
    </article>
  );
}

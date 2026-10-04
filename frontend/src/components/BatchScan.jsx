import { useEffect, useState } from "react";
import { Link } from "react-router";
import { createTransactionsBatch } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { inr, when } from "../lib/format.js";
import { createOcr } from "../lib/ocr.js";
import { missingFor, toTransaction } from "../lib/scanBatch.js";
import { Level } from "./ui.jsx";

const STATUS_TEXT = { queued: "Waiting", reading: "Reading…", done: "Read", failed: "Couldn't read" };

/**
 * Reads several screenshots one after another with a single OCR engine (all in the browser), lists what
 * was found, and lets the user load one into the form or save all of them to their history.
 */
export default function BatchScan({ files, onUse, onClose }) {
  const { user } = useAuth();
  const [items, setItems] = useState(() => files.map((file, i) => ({
    id: i, file, status: "queued", progress: 0, parsed: null,
  })));
  const [urls, setUrls] = useState([]);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const update = (id, patch) => setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  // Thumbnails: created and revoked by the same effect run (safe under StrictMode's double run).
  useEffect(() => {
    const made = files.map((f) => URL.createObjectURL(f));
    setUrls(made);
    return () => made.forEach((u) => URL.revokeObjectURL(u));
  }, [files]);

  // Read the screenshots one by one with one OCR engine. Each run has its own stop flag, so a run that
  // is cleaned up (unmount, StrictMode re-run) stops at its next step and never writes stale results.
  useEffect(() => {
    let stop = false;
    setItems((xs) => xs.map((x) => ({ ...x, status: "queued", progress: 0, parsed: null })));
    (async () => {
      let ocr;
      try {
        ocr = await createOcr();
      } catch {
        if (!stop) {
          setItems((xs) => xs.map((x) => ({ ...x, status: "failed" })));
          setError("The text reader couldn't start (it needs internet the first time).");
        }
        return;
      }
      try {
        for (let i = 0; i < files.length && !stop; i++) {
          update(i, { status: "reading" });
          try {
            const parsed = await ocr.read(files[i], (p) => !stop && update(i, { progress: p }));
            if (!stop) update(i, { status: "done", progress: 100, parsed });
          } catch {
            if (!stop) update(i, { status: "failed" });
          }
        }
      } finally {
        ocr.close();
      }
    })();
    return () => { stop = true; };
  }, [files]);

  const done = items.filter((x) => x.status === "done" || x.status === "failed").length;
  const ready = items.filter((x) => x.status === "done" && missingFor(x.parsed).length === 0 && !x.removed);
  const finished = done === items.length;

  async function saveAll() {
    setSaving(true);
    setError("");
    try {
      const r = await createTransactionsBatch(ready.map((x) => toTransaction(x.parsed)));
      setResult({ ...r, sent: ready.length });
      window.dispatchEvent(new Event("upig:alerts"));
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="batch" aria-live="polite">
      <div className="batch-head">
        <p className="label">{finished ? `Read ${items.length} screenshots` : `Reading ${done + 1 > items.length ? items.length : done + 1} of ${items.length}…`}</p>
        <button type="button" className="textbtn" onClick={onClose}>{finished ? "Clear" : "Cancel"}</button>
      </div>
      <div className="progress"><div style={{ width: (done / items.length) * 100 + "%" }} /></div>

      <ul className="batch-list">
        {items.filter((x) => !x.removed).map((x) => {
          const p = x.parsed;
          const missing = p ? missingFor(p) : [];
          return (
            <li key={x.id} className={"batch-item " + x.status}>
              {urls[x.id] ? <img src={urls[x.id]} alt={`Screenshot ${x.id + 1}`} /> : <span />}
              <div className="batch-body">
                {x.status === "done" ? (
                  <>
                    <p className="batch-amount">
                      {p.amount ? <>{p.direction === "received" ? "+" : p.direction === "sent" ? "−" : ""}{inr(p.amount)}</> : "Amount not found"}
                      {p.direction && <span className="label"> {p.direction}</span>}
                    </p>
                    <p className="batch-meta">
                      {[p.payee || p.payeeUpi, p.app, p.date && p.time
                        ? when(new Date(p.date.y, p.date.mo, p.date.d, p.time.h, p.time.min).toISOString())
                        : null, p.txnId && `Ref ${p.txnId}`].filter(Boolean).join(" · ") || "No other details found"}
                    </p>
                    {missing.length > 0 && <p className="warn-note">Missing {missing.join(" and ")}. Use it in the form to fill that in.</p>}
                  </>
                ) : (
                  <p className="batch-meta">{STATUS_TEXT[x.status]}{x.status === "reading" && ` ${x.progress}%`}</p>
                )}
              </div>
              <div className="batch-actions">
                {x.status === "done" && <button type="button" className="ghost small" onClick={() => onUse(p)}>Use in form</button>}
                {finished && <button type="button" className="textbtn" onClick={() => update(x.id, { removed: true })}
                                     aria-label={`Remove screenshot ${x.id + 1}`}>Remove</button>}
              </div>
            </li>
          );
        })}
      </ul>

      {finished && !result && (
        user ? (
          <div className="batch-save">
            <button type="button" className="primary small" disabled={saving || ready.length === 0} onClick={saveAll}>
              {saving ? "Saving…" : `Save ${ready.length} to history`}
            </button>
            <p className="note">
              Each payment is scored against your history (new recipient, rapid transfers, repeated payments…).
              Receipts don't show your balance, so the ML model scores a payment only after you add its balance on the
              investigation page. Payments already in your history (same reference) are skipped.
            </p>
          </div>
        ) : (
          <p className="note"><Link to="/login?next=/check">Sign in</Link> to save all of them to your history at once,
            or use one at a time in the form below.</p>
        )
      )}

      {result && (
        <div className="notice" role="status">
          Saved {result.saved.length} payment{result.saved.length === 1 ? "" : "s"}
          {result.skipped.length > 0 && <>, skipped {result.skipped.length} already in your history</>}
          {result.high_risk > 0 && <> · <b>{result.high_risk} high risk</b></>}.
          <ul className="batch-saved">
            {result.saved.map((t) => (
              <li key={t.id}><Link to={`/investigate/${t.id}`}>{inr(t.amount)} {t.direction === "received" ? "from" : "to"} {t.counterparty_upi || t.counterparty_name || "unknown"}</Link>{" "}
                <Level level={t.risk_level}>{Math.round((t.risk_score || 0) * 100)}</Level></li>
            ))}
          </ul>
          <Link to="/transactions">Open history →</Link>
        </div>
      )}
      {error && <p className="error-box" role="alert">{error}</p>}
    </div>
  );
}

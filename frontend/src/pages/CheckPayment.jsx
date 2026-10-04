import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import BatchScan from "../components/BatchScan.jsx";
import Verdict from "../components/Verdict.jsx";
import { checkReceived, createTransaction, predict } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { inr, localDateTime } from "../lib/format.js";
import { createOcr, IMAGE_TYPES, MAX_BATCH_IMAGES, MAX_IMAGE_BYTES } from "../lib/ocr.js";

// Simple, guided check for people who aren't technical: who paid whom -> details -> answer.
// The full form with every field is still at /check/detailed.

const QUESTIONS = [
  ["inBank", "Has the money reached YOUR bank account?",
   "Check your own bank app or bank SMS, not the customer's phone or screenshot."],
  ["knowsSender", "Do you know this person?", "For example a regular customer, family or a friend."],
  ["askedToPay", "Did they ask you to send money back, give change, or pay a fee?",
   "For example \"I paid extra by mistake, please return it\"."],
];
const ANSWERS = [["yes", "Yes"], ["no", "No"], ["unsure", "Not sure"]];
const STATUS = { Successful: "success", Failed: "failed", Pending: "pending" };
const num = (v) => (String(v ?? "").trim() === "" ? null : Number(v));

const empty = () => ({ amount: "", when: localDateTime(), name: "", upi: "", ref: "", status: "", app: null,
  balBefore: "", balAfter: "", destBefore: "", destAfter: "", inBank: "", knowsSender: "", askedToPay: "" });

export default function CheckPayment() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [kind, setKind] = useState(null);           // "received" | "sent"
  const [f, setF] = useState(empty);
  const [shot, setShot] = useState(null);           // { url, status: reading|done|failed, note }
  const [batch, setBatch] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [saved, setSaved] = useState(null);
  const top = useRef(null);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const step = !kind ? 1 : result ? 3 : 2;

  function start(k) {
    setKind(k);
    setResult(null);
    setError("");
  }
  function reset() {
    setKind(null); setF(empty()); setShot(null); setBatch(null); setResult(null); setSaved(null); setError("");
    top.current?.scrollIntoView({ behavior: "smooth" });
  }

  // Fill the fields from a screenshot (OCR runs on this device).
  function apply(p) {
    setF((x) => {
      const d = p.date ? new Date(p.date.y, p.date.mo, p.date.d) : new Date();
      const t = p.time || (p.date ? { h: 12, min: 0 } : null);
      return {
        ...x,
        amount: p.amount ? String(p.amount) : x.amount,
        when: t ? localDateTime(d, t.h, t.min) : x.when,
        name: p.payee || x.name,
        upi: p.payeeUpi && !p.payeeUpi.startsWith("•") ? p.payeeUpi : x.upi,
        ref: p.txnId || x.ref,
        status: p.status || x.status,
        app: p.app || x.app,
      };
    });
    const other = p.direction && p.direction !== kind ? p.direction : null;
    return other;
  }

  async function pick(list) {
    const files = [...(list || [])].filter((x) => IMAGE_TYPES.test(x.type) && x.size <= MAX_IMAGE_BYTES).slice(0, MAX_BATCH_IMAGES);
    if (!files.length) return setError("Please choose a photo or screenshot (PNG or JPG).");
    setError("");
    if (files.length > 1) { setShot(null); setBatch(files); return; }
    setBatch(null);
    const url = URL.createObjectURL(files[0]);
    setShot({ url, status: "reading" });
    try {
      const ocr = await createOcr();
      const p = await ocr.read(files[0]);
      ocr.close();
      const other = apply(p);
      const found = p.amount ? `We read ${inr(p.amount)}${p.payee ? (p.direction === "received" ? " from " : " to ") + p.payee : ""}.` : "We couldn't read the amount. Please type it.";
      setShot({ url, status: "done", note: found, other });
    } catch {
      setShot({ url, status: "failed", note: "Couldn't read this picture. Please type the amount." });
    }
  }

  async function check(e) {
    e.preventDefault();
    setError("");
    const amount = num(f.amount);
    if (!amount || amount <= 0) return setError("Please enter the amount.");
    if (!f.when) return setError("Please enter the date and time.");
    const hour = new Date(f.when).getHours();
    if (kind === "received" && QUESTIONS.some(([k]) => !f[k])) return setError("Please answer all three questions.");
    if (kind === "sent" && num(f.balBefore) === null) return setError("Please enter your bank balance before this payment (it's in your bank SMS).");
    setBusy(true);
    try {
      const r = kind === "received"
        ? await checkReceived({ amount, hour, knows_sender: f.knowsSender, in_bank: f.inBank, asked_to_pay: f.askedToPay })
        : await predict({ type: "TRANSFER", amount, hour, sender_balance_before: num(f.balBefore),
                          sender_balance_after: num(f.balAfter), receiver_balance_before: num(f.destBefore),
                          receiver_balance_after: num(f.destAfter) });
      setResult(r);
      setTimeout(() => top.current?.scrollIntoView({ behavior: "smooth" }), 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    try {
      const received = kind === "received";
      const tx = await createTransaction({
        occurred_at: f.when, direction: kind, amount: num(f.amount),
        counterparty_name: f.name || null,
        counterparty_upi: /^[a-z0-9][a-z0-9._-]{1,255}@[a-z][a-z0-9]{1,63}$/i.test(f.upi) ? f.upi : null,
        external_id: /^[A-Za-z0-9-]{4,64}$/.test(f.ref) ? f.ref : null,
        status: STATUS[f.status] || "success", payment_app: f.app,
        balance_before: received ? null : num(f.balBefore), balance_after: received ? null : num(f.balAfter),
        receiver_balance_before: received ? null : num(f.destBefore),
        receiver_balance_after: received ? null : num(f.destAfter),
        received_answers: received ? { knows_sender: f.knowsSender, in_bank: f.inBank, asked_to_pay: f.askedToPay } : null,
        source: shot ? "screenshot" : "manual",
      });
      setSaved(tx);
      window.dispatchEvent(new Event("upig:alerts"));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="guided" ref={top}>
      <ol className="stepper" aria-label="Steps">
        {["Who paid?", "Details", "Result"].map((s, i) => (
          <li key={s} className={step === i + 1 ? "on" : step > i + 1 ? "done" : ""} aria-current={step === i + 1 ? "step" : undefined}>
            <span>{step > i + 1 ? "✓" : i + 1}</span>{s}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <>
          <h1 className="guided-title">Which payment do you want to check?</h1>
          <div className="choice-grid">
            <button type="button" className="choice" onClick={() => start("received")}>
              <span className="choice-icon" aria-hidden="true">↓₹</span>
              <span className="choice-title">A customer paid me</span>
              <span className="choice-text">Someone shows you a payment screen or says they've paid.</span>
            </button>
            <button type="button" className="choice" onClick={() => start("sent")}>
              <span className="choice-icon" aria-hidden="true">₹↑</span>
              <span className="choice-title">I paid someone</span>
              <span className="choice-text">Check a payment that went out of your account.</span>
            </button>
          </div>
          <p className="muted small-print">Need every field? <Link to="/check/detailed">Use the detailed check</Link>.</p>
        </>
      )}

      {step === 2 && (
        <form onSubmit={check} noValidate>
          <h1 className="guided-title">{kind === "received" ? "Check a payment you received" : "Check a payment you made"}</h1>
          <button type="button" className="textbtn" onClick={() => setKind(null)}>← Change</button>

          <div className="shot-box">
            <label className="big-btn ghost-btn file-btn">
              <input type="file" accept="image/*" multiple onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
              📷 Add payment screenshot or photo
            </label>
            <p className="muted small-print">Optional. We read the amount and name for you. Pictures stay on this phone.</p>
            {shot && (
              <div className="shot-result">
                <img src={shot.url} alt="Your screenshot" />
                <div>
                  <p>{shot.status === "reading" ? "Reading the picture…" : shot.note}</p>
                  {shot.other && (
                    <p className="warn-note">This looks like money you {shot.other}.{" "}
                      <button type="button" className="textbtn" onClick={() => setKind(shot.other)}>Switch</button></p>
                  )}
                </div>
              </div>
            )}
            {batch && <BatchScan key={batch.map((x) => x.name + x.size).join("|")} files={batch}
                                 onUse={(p) => { apply(p); setBatch(null); }} onClose={() => setBatch(null)} />}
          </div>

          <div className="field big-field">
            <label htmlFor="amount">Amount</label>
            <div className="money"><input id="amount" type="number" inputMode="decimal" min="1" step="0.01"
                                          value={f.amount} onChange={(e) => set("amount", e.target.value)} placeholder="0" /></div>
          </div>
          <div className="field big-field">
            <label htmlFor="when">Date and time of payment</label>
            <input id="when" type="datetime-local" value={f.when} onChange={(e) => set("when", e.target.value)} />
          </div>

          {kind === "received" ? (
            QUESTIONS.map(([k, q, hint]) => (
              <fieldset key={k} className="big-question">
                <legend>{q}</legend>
                <p className="muted small-print">{hint}</p>
                <div className="answer-row">
                  {ANSWERS.map(([v, label]) => (
                    <label key={v} className={"answer" + (f[k] === v ? " on" : "")}>
                      <input type="radio" name={k} value={v} checked={f[k] === v} onChange={() => set(k, v)} />
                      {label}
                    </label>
                  ))}
                </div>
              </fieldset>
            ))
          ) : (
            <>
              <div className="field big-field">
                <label htmlFor="balBefore">Your bank balance before this payment</label>
                <p className="muted small-print">It's in the bank SMS you got for this payment.</p>
                <div className="money"><input id="balBefore" type="number" inputMode="decimal" min="0" step="0.01"
                                              value={f.balBefore} onChange={(e) => set("balBefore", e.target.value)} /></div>
              </div>
              <details className="more-details">
                <summary>More details (optional)</summary>
                <div className="field"><label htmlFor="balAfter">Balance after the payment</label>
                  <div className="money"><input id="balAfter" type="number" min="0" value={f.balAfter} onChange={(e) => set("balAfter", e.target.value)} /></div></div>
                <div className="field"><label htmlFor="destBefore">Receiver's balance before (only if you know it)</label>
                  <div className="money"><input id="destBefore" type="number" min="0" value={f.destBefore} onChange={(e) => set("destBefore", e.target.value)} /></div></div>
                <div className="field"><label htmlFor="destAfter">Receiver's balance after</label>
                  <div className="money"><input id="destAfter" type="number" min="0" value={f.destAfter} onChange={(e) => set("destAfter", e.target.value)} /></div></div>
              </details>
            </>
          )}

          {error && <p className="error-box" role="alert">{error}</p>}
          <button type="submit" className="big-btn primary-btn" disabled={busy}>{busy ? "Checking…" : "Check this payment"}</button>
        </form>
      )}

      {step === 3 && (
        <>
          <Verdict kind={kind} level={result.risk} reasons={result.reasons.filter((r) => r.direction !== "down").length
            ? result.reasons.filter((r) => r.direction !== "down") : result.reasons} />
          <p className="muted small-print">
            {inr(f.amount)} {kind === "received" ? "received" : "paid"}{f.name ? ` · ${f.name}` : ""}
            {result.probability != null && ` · fraud score ${(result.probability * 100).toFixed(result.probability < 0.01 ? 2 : 1)}%`}
          </p>
          {kind === "received" && result.risk !== "low" && (
            <ul className="do-list">
              <li>Wait until the money shows in <b>your</b> bank app or bank SMS before handing over goods.</li>
              <li>Never enter your UPI PIN or scan a QR to receive money.</li>
              <li>Don't send money back yourself. A real mistake is fixed by the sender's bank.</li>
            </ul>
          )}
          <div className="result-actions">
            {user ? (
              saved ? <Link className="big-btn ghost-btn" to={`/investigate/${saved.id}`}>Saved. Open in My payments →</Link>
                : <button type="button" className="big-btn ghost-btn" onClick={save} disabled={busy}>Save to My payments</button>
            ) : (
              <Link className="big-btn ghost-btn" to="/login?next=/check">Sign in to save it</Link>
            )}
            <button type="button" className="big-btn primary-btn" onClick={reset}>Check another payment</button>
          </div>
          {error && <p className="error-box" role="alert">{error}</p>}
        </>
      )}
    </div>
  );
}

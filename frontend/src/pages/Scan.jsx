import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import QrScanner from "../components/QrScanner.jsx";
import Verdict from "../components/Verdict.jsx";
import { ErrorNote, TxRow } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { inr, when } from "../lib/format.js";

const TABS = [["message", "Message"], ["url", "Link"], ["qr", "QR code"], ["upi", "UPI ID"]];
const VERDICT_LEVEL = { "HIGH RISK": "high", SUSPICIOUS: "medium", SAFE: "low", UNKNOWN: "unknown" };
const EXAMPLES = {
  message: "Dear customer, your SBI account will be blocked today. Update KYC immediately: http://sbi-kyc-update.example/verify or share the OTP with our executive.",
  url: "http://sbi-secure-login.xyz/kyc/update",
  qr: "upi://pay?pa=cashback.reward@ybl&pn=Cashback%20Reward&am=2000&cu=INR&tn=Scan%20to%20receive%20cashback",
  upi: "kyc.refund.helpdesk@ybl",
};

const CHOICES = [
  ["qr", "▦", "Scan a QR code", "Before you pay at a QR, or if someone sends you one."],
  ["upi", "@", "Check a UPI ID", "Someone asks you to pay to a UPI ID or number."],
  ["url", "↗", "Check a link", "A payment or \"KYC\" link you were sent."],
  ["message", "✉", "Check a message", "An SMS or WhatsApp message that looks suspicious."],
];

export default function Scan() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([t]) => t === params.get("tab")) ? params.get("tab") : null;
  const setTab = (t) => setParams(t ? { tab: t } : {}, { replace: false });
  const current = CHOICES.find(([id]) => id === tab);

  return (
    <div className="guided">
      {!tab ? (
        <>
          <h1 className="guided-title">Check before you pay</h1>
          <p className="lede">What do you want to check? Nothing you check is saved, and links are never opened.</p>
          <div className="choice-grid four">
            {CHOICES.map(([id, icon, title, text]) => (
              <button key={id} type="button" className="choice" onClick={() => setTab(id)}>
                <span className="choice-icon" aria-hidden="true">{icon}</span>
                <span className="choice-title">{title}</span>
                <span className="choice-text">{text}</span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <>
          <button type="button" className="textbtn" onClick={() => setTab(null)}>← Check something else</button>
          <h1 className="guided-title">{current[2]}</h1>
          {tab === "message" && <MessageScan />}
          {tab === "url" && <UrlScan />}
          {tab === "qr" && <QrScan />}
          {tab === "upi" && <UpiScan initial={params.get("vpa") || ""} />}
        </>
      )}
    </div>
  );
}

function useRun(fn) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async (...args) => {
    setBusy(true);
    setError(null);
    try { setResult(await fn(...args)); } catch (e) { setError(e); setResult(null); } finally { setBusy(false); }
  };
  return { result, error, busy, run, setResult };
}

function MessageScan() {
  const [text, setText] = useState("");
  const { result, error, busy, run } = useRun(api.analyzeMessage);
  return (
    <div className="scan-grid">
      <form onSubmit={(e) => { e.preventDefault(); run(text); }}>
        <div className="field">
          <label htmlFor="msg">Paste the SMS, WhatsApp or email text</label>
          <textarea id="msg" rows={7} maxLength={5000} value={text} onChange={(e) => setText(e.target.value)}
                    placeholder="English, Hinglish or Hindi" />
        </div>
        <div className="row-actions">
          <button type="submit" className="big-btn primary-btn" disabled={busy || !text.trim()}>{busy ? "Scanning…" : "Scan message"}</button>
          <button type="button" className="textbtn" onClick={() => setText(EXAMPLES.message)}>Use an example</button>
        </div>
        <p className="note">Tip: a screenshot of a message can be read with the <Link to="/check">screenshot reader</Link>; paste its text here.</p>
      </form>
      <div>
        <ErrorNote error={error} />
        {result && (
          <ResultBox level={result.level} title={result.level === "low" ? "No known scam indicators" : result.likely_scam.join(" / ")} summary={result.summary}>
            {result.indicators.length > 0 && (
              <ul className="signals">{result.indicators.map((i) => <li key={i.code}><b>{i.category}</b> {i.text}</li>)}</ul>
            )}
            <Extracted ex={result.extracted} />
          </ResultBox>
        )}
      </div>
    </div>
  );
}

function Extracted({ ex }) {
  const rows = [["Links", ex.urls.map((u) => `${u.url} (${u.verdict.toLowerCase()})`)], ["UPI IDs", ex.upi_ids],
                ["Phone numbers", ex.phones], ["Amounts", ex.amounts.map(inr)], ["Names used", ex.brands]].filter(([, v]) => v.length);
  if (!rows.length) return null;
  return (
    <dl className="lines extracted">
      {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><span className="leader" /><dd>{v.join(", ")}</dd></div>)}
    </dl>
  );
}

function UrlScan() {
  const [url, setUrl] = useState("");
  const { result, error, busy, run } = useRun(api.analyzeUrl);
  return (
    <div className="scan-grid">
      <form onSubmit={(e) => { e.preventDefault(); run(url); }}>
        <div className="field">
          <label htmlFor="url">Payment or login link</label>
          <input id="url" type="text" inputMode="url" maxLength={2000} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
        </div>
        <div className="row-actions">
          <button type="submit" className="big-btn primary-btn" disabled={busy || !url.trim()}>{busy ? "Checking…" : "Check link"}</button>
          <button type="button" className="textbtn" onClick={() => setUrl(EXAMPLES.url)}>Use an example</button>
        </div>
        <p className="note">We only look at the address. We don't open the page, so redirects and page content aren't checked.</p>
      </form>
      <div>
        <ErrorNote error={error} />
        {result && (
          <ResultBox level={VERDICT_LEVEL[result.verdict]} title={result.verdict} summary={result.summary}>
            {result.url && <p className="note">Domain: <b>{result.url.domain}</b>{result.url.official ? " (known official)" : ""}</p>}
            <ul className="signals">{result.signals.map((s) => <li key={s.code} className={s.kind}>{s.text}</li>)}</ul>
            <p className="note">Basis: {result.basis}</p>
          </ResultBox>
        )}
      </div>
    </div>
  );
}

function QrScan() {
  const [payload, setPayload] = useState("");
  const { result, error, busy, run } = useRun(api.analyzeQr);
  const analyze = (p) => { setPayload(p); run(p); };
  const pay = result?.payment;
  return (
    <div className="scan-grid">
      <div>
        <QrScanner onDecoded={analyze} />
        <form onSubmit={(e) => { e.preventDefault(); run(payload); }}>
          <div className="field">
            <label htmlFor="qrtext">…or paste a UPI link</label>
            <input id="qrtext" type="text" maxLength={2000} value={payload} onChange={(e) => setPayload(e.target.value)} placeholder="upi://pay?pa=…" />
          </div>
          <div className="row-actions">
            <button type="submit" className="big-btn primary-btn" disabled={busy || !payload.trim()}>Check</button>
            <button type="button" className="textbtn" onClick={() => analyze(EXAMPLES.qr)}>Use an example</button>
          </div>
        </form>
      </div>
      <div>
        <ErrorNote error={error} />
        {result && (
          <ResultBox level={result.level} title={result.kind === "upi" ? "QR payment" : result.kind === "url" ? "Web link QR" : "Not a payment QR"} summary={result.summary}>
            {pay && (
              <dl className="lines">
                <div><dt>Payee</dt><span className="leader" /><dd>{pay.payee_name || "–"}</dd></div>
                <div><dt>UPI ID</dt><span className="leader" /><dd>{pay.payee_vpa || "missing"}</dd></div>
                {pay.app && <div><dt>App / bank</dt><span className="leader" /><dd>{pay.app} · {pay.bank}</dd></div>}
                <div><dt>Amount</dt><span className="leader" /><dd>{pay.amount ? inr(pay.amount) : "not pre-filled"}</dd></div>
                {pay.note && <div><dt>Note</dt><span className="leader" /><dd>{pay.note}</dd></div>}
                {pay.merchant_code && <div><dt>Merchant code</dt><span className="leader" /><dd>{pay.merchant_code}</dd></div>}
              </dl>
            )}
            {result.warnings.length > 0 && <ul className="signals">{result.warnings.map((w) => <li key={w.code}>{w.text}</li>)}</ul>}
            <p className="note">Scanning a QR always <b>sends</b> money. Nobody can pay you by asking you to scan.</p>
          </ResultBox>
        )}
      </div>
    </div>
  );
}

function UpiScan({ initial }) {
  const { user } = useAuth();
  const [vpa, setVpa] = useState(initial);
  const { result, error, busy, run } = useRun(api.checkUpi);
  useEffect(() => { if (initial) run(initial); }, [initial]);  // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="scan-grid">
      <form onSubmit={(e) => { e.preventDefault(); run(vpa.trim()); }}>
        <div className="field">
          <label htmlFor="vpa">UPI ID</label>
          <input id="vpa" type="text" maxLength={300} value={vpa} onChange={(e) => setVpa(e.target.value)} placeholder="name@bank" autoCapitalize="none" />
        </div>
        <div className="row-actions">
          <button type="submit" className="big-btn primary-btn" disabled={busy || !vpa.trim()}>Check UPI ID</button>
          <button type="button" className="textbtn" onClick={() => setVpa(EXAMPLES.upi)}>Use an example</button>
        </div>
      </form>
      <div>
        <ErrorNote error={error} />
        {result && (
          <ResultBox level={result.level} title={result.vpa} summary={result.valid ? (result.app ? `${result.app} · ${result.bank}` : "Valid format") : "Invalid UPI ID"}>
            {result.signals.length > 0 && <ul className="signals">{result.signals.map((s) => <li key={s.code} className={s.severity}>{s.text}</li>)}</ul>}
            <p className="note">Community reports: <b>{result.reports.total_reporters}</b>
              {Object.entries(result.reports.by_category).map(([c, n]) => ` · ${c.replace("_", " ")} ${n}`)}. {result.reports.note}</p>
            {result.history ? (
              result.history.count ? (
                <>
                  <p className="label">Your history with this ID</p>
                  <p>{result.history.count} payments · sent {inr(result.history.total_sent)} · received {inr(result.history.total_received)} · first {when(result.history.first_seen)}</p>
                  <ul className="tx-list">{result.history.recent.map((t) => <TxRow key={t.id} t={{ ...t, counterparty_upi: result.vpa, review_status: "unreviewed" }} compact />)}</ul>
                </>
              ) : <p className="muted">You haven't transacted with this UPI ID.</p>
            ) : <p className="note"><Link to="/login?next=/before-you-pay?tab=upi">Sign in</Link> to compare with your own history.</p>}
            {result.valid && user && <Link to={`/reports?vpa=${encodeURIComponent(result.vpa)}`}>Report this UPI ID →</Link>}
          </ResultBox>
        )}
      </div>
    </div>
  );
}

function ResultBox({ level, title, summary, children }) {
  // Plain verdict first; the specific warnings stay visible underneath.
  return (
    <Verdict kind="check" level={level || "unknown"}>
      <div className="verdict-details">
        <p className="verdict-sub">{title}</p>
        <p className="small-print">{summary}</p>
        {children}
      </div>
    </Verdict>
  );
}

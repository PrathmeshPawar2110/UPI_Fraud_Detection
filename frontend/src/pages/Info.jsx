import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ErrorNote, Loading, PageHead } from "../components/ui.jsx";
import { getMonitoring } from "../lib/api.js";

export function Privacy() {
  return (
    <div className="prose">
      <PageHead kicker="Privacy first" title="How UPI Guard handles your data" />
      <h2>What we never ask for or store</h2>
      <p>Your UPI PIN, OTPs, bank or card passwords, card numbers or CVV. If one is pasted into case evidence or a note,
        it's masked before saving.</p>
      <h2>Screenshots and QR codes</h2>
      <p>Read on your device (Tesseract.js and jsQR in the browser). The image is never uploaded; only the fields you
        confirm are sent. The OCR engine and its language data are downloaded from public CDNs the first time.</p>
      <h2>What's stored when you have an account</h2>
      <p>Transactions you save or import, their risk scores, cases, evidence text, notes, alerts and your reports. Stored
        in the app's database and visible only to your account.</p>
      <h2>Community reports</h2>
      <p>When you report a UPI ID, number or link, other users see only the number of distinct reporters per scam
        category. Never who reported it or what you wrote. Reports are unverified and are not an official list.</p>
      <h2>AI investigator</h2>
      <p>Off by default. When you turn it on and ask a question, the question and the records needed to answer it are
        sent to the AI provider this server is configured with (Anthropic, OpenAI, Azure OpenAI or Google Gemini; the
        provider is named in Settings before you turn it on). The model only receives records returned by tools scoped
        to your account. There's a daily limit per user.</p>
      <h2>Your controls</h2>
      <p>Export everything as JSON, delete your history, set automatic deletion, or delete your account in
        <Link to="/settings"> Settings</Link>.</p>
      <h2>Security</h2>
      <p>Passwords are hashed with scrypt; sessions use signed, HttpOnly, SameSite=Strict cookies; failed logins are
        throttled; requests are size-limited and validated; security headers are set; account actions are audit-logged.</p>
    </div>
  );
}

export function Model() {
  const [m, setM] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { getMonitoring().then(setM).catch(setError); }, []);
  if (error) return <ErrorNote error={error} />;
  if (!m) return <Loading />;
  const rows = [["with_receiver_balances", "Model, receiver balances known"], ["without_receiver_balances", "Model, receiver balances unknown"],
                ["baseline_isFlaggedFraud", "Rule: simulator flag"], ["baseline_amount_over_200k", "Rule: amount > 2 lakh"],
                ["baseline_empties_account", "Rule: sends entire balance"]];
  const max = Math.max(1, ...(m.live?.probability_histogram || []).map((b) => b.count));
  return (
    <>
      <PageHead kicker="For the project team" title="Model monitoring">
        {m.model.type}, best iteration {m.model.best_iteration}. Trained on {m.model.dataset}.
      </PageHead>
      <section className="sec">
        <div className="sec-head"><span className="sec-no">Test</span><h2>Test-set metrics</h2>
          <span className="sec-aside">thresholds: high ≥ {m.thresholds.high.toFixed(4)}, medium ≥ {m.thresholds.medium.toFixed(4)}</span></div>
        <table className="report-table">
          <thead><tr><th>Scorer</th><th>PR-AUC</th><th>Precision</th><th>Recall</th><th>F1</th><th>FP</th><th>FN</th></tr></thead>
          <tbody>{rows.map(([k, label]) => { const x = m.test_metrics[k]; return (
            <tr key={k}><td>{label}</td><td>{x.pr_auc?.toFixed(3)}</td><td>{(x.precision * 100).toFixed(1)}%</td><td>{(x.recall * 100).toFixed(1)}%</td>
              <td>{x.f1?.toFixed(3)}</td><td>{x.confusion?.fp}</td><td>{x.confusion?.fn}</td></tr>); })}</tbody>
        </table>
        <p className="note">PaySim is close to separable, so these numbers won't carry over to real UPI fraud. Feature drift: {m.drift}</p>
      </section>
      {m.live ? (
        <section className="sec">
          <div className="sec-head"><span className="sec-no">Live</span><h2>Your scored transactions</h2></div>
          <p>{m.live.scored} scored ({m.live.model_scored} by the model) · low {m.live.by_level.low} · medium {m.live.by_level.medium} · high {m.live.by_level.high}</p>
          <ul className="histogram" aria-label="Model probability distribution">
            {m.live.probability_histogram.map((b) => (
              <li key={b.from}><span className="h-label">{(b.from * 100).toFixed(0)}–{(b.to * 100).toFixed(0)}%</span>
                <span className="h-bar"><span style={{ width: (b.count / max) * 100 + "%" }} /></span><span className="h-count">{b.count}</span></li>
            ))}
          </ul>
          <p className="note">Your reviews: {m.live.reviewed.legitimate} legitimate, {m.live.reviewed.suspicious} suspicious,
            {" "}{m.live.reviewed.confirmed_fraud} confirmed fraud · possible false positives (high but marked legitimate): {m.live.false_positive_candidates}
            {" "}· possible misses (low but confirmed fraud): {m.live.missed_candidates}</p>
        </section>
      ) : <p className="note"><Link to="/login?next=/model">Sign in</Link> to see the distribution over your own transactions.</p>}
      <section className="sec">
        <div className="sec-head"><span className="sec-no">Features</span><h2>Feature importance (gain)</h2></div>
        <ul className="histogram">{m.feature_importance.map(([f, v]) => (
          <li key={f}><span className="h-label"><code>{f}</code></span><span className="h-bar"><span style={{ width: v * 100 + "%" }} /></span><span className="h-count">{(v * 100).toFixed(1)}%</span></li>))}</ul>
      </section>
    </>
  );
}

export function NotFound() {
  return (
    <div className="narrow">
      <h1 className="page-title">Page not found</h1>
      <p><Link to="/">Go home</Link> or <Link to="/check">check a payment</Link>.</p>
    </div>
  );
}

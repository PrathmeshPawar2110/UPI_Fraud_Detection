import { useEffect, useState } from "react";
import { Link } from "react-router";
import { getGuidance } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { FALLBACK } from "./Emergency.jsx";
import { SCAMS } from "./Learn.jsx";

// Scams merchants meet most often come first.
const MERCHANT_ORDER = ["screenshot", "wrong", "upi", "qr", "otp", "kyc", "support", "remote", "investment", "social"];

export default function Help() {
  const { user } = useAuth();
  const [g, setG] = useState(FALLBACK);
  const [open, setOpen] = useState("screenshot");
  useEffect(() => { getGuidance().then(setG).catch(() => {}); }, []);
  const scams = MERCHANT_ORDER.map((id) => SCAMS.find((s) => s.id === id)).filter(Boolean);

  return (
    <div className="help-page">
      <h1 className="guided-title">Help</h1>

      <section className="help-urgent">
        <h2>Lost money, or think you're being scammed?</h2>
        <p>Act fast. The first hours give the best chance of stopping the money.</p>
        <a className="big-btn danger-btn" href="tel:1930">Call 1930 now <small>National Cyber Crime Helpline</small></a>
        <ol className="emergency-steps">
          {g.steps.map((s, i) => (
            <li key={s.title}><span className="step-no">{i + 1}</span><div><h3>{s.title}</h3><p>{s.text}</p></div></li>
          ))}
        </ol>
        <p className="small-print">
          Report online at <a href="https://cybercrime.gov.in" target="_blank" rel="noopener noreferrer">cybercrime.gov.in</a>.
          Scam call or SMS, but no money lost? Report it on{" "}
          <a href="https://sancharsaathi.gov.in" target="_blank" rel="noopener noreferrer">Sanchar Saathi (Chakshu)</a>.
          UPI Guard can't block accounts or get money back; only your bank and the police can.
        </p>
      </section>

      <section>
        <h2 className="sub-title">Common scams and how to spot them</h2>
        <ul className="learn-grid single">
          {scams.map((s) => (
            <li key={s.id} className={open === s.id ? "open" : ""}>
              <button type="button" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
                <span>{s.title}</span><span aria-hidden="true">{open === s.id ? "−" : "+"}</span>
              </button>
              {open === s.id && (
                <div className="learn-body">
                  <p>{s.how}</p>
                  <p className="verdict-sub">Warning signs</p>
                  <ul className="plain">{s.flags.map((f) => <li key={f}>{f}</li>)}</ul>
                  <p className="verdict-sub">What to do</p>
                  <p>{s.act}</p>
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="help-more">
        <h2 className="sub-title">More</h2>
        <ul className="link-list">
          <li><Link to="/learn">Practise: spot the scam (quiz)</Link></li>
          <li><Link to={user ? "/reports" : "/login?next=/reports"}>Report a scammer's UPI ID, number or link</Link></li>
          <li><Link to="/privacy">How your data is kept private</Link></li>
        </ul>
      </section>
    </div>
  );
}

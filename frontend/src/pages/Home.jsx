import { Link } from "react-router";
import { useAuth } from "../lib/auth.jsx";

const STEPS = [
  ["01", "Check", "Upload a GPay, PhonePe, Paytm or BHIM screenshot. It's read on your device; only the numbers you confirm are scored."],
  ["02", "Explain", "See which signals raised the risk: the ML model's reasons, rules for money you received, and patterns in your own history."],
  ["03", "Investigate", "Follow the timeline, related payments and the recipient's connections. Add notes and open a case."],
  ["04", "Act", "Get the right next step: your bank, 1930, cybercrime.gov.in or Chakshu, with an incident report to share."],
];

const SCANS = [
  ["/check", "Payment screenshot", "OCR in the browser, then the fraud model and your history."],
  ["/scan?tab=message", "SMS / WhatsApp message", "KYC threats, OTP requests, fake refunds, digital arrest (English & Hinglish)."],
  ["/scan?tab=url", "Payment link", "Look-alike domains, shorteners, brand mismatch. We never open the link."],
  ["/scan?tab=qr", "QR code", "Decodes the UPI payment inside and warns about 'scan to receive' tricks."],
  ["/scan?tab=upi", "UPI ID", "Format, payment app, warning signs and unverified community reports."],
  ["/transactions?import=1", "Statement (CSV)", "Import past payments so patterns like new recipients and bursts can be spotted."],
];

export default function Home() {
  const { user } = useAuth();
  return (
    <div className="home">
      <section className="hero">
        <p className="label">UPI Guard · fraud detection, investigation & prevention</p>
        <h1>Protect every <em>UPI payment.</em></h1>
        <p className="lede">
          Detect suspicious transactions, understand fraud signals, investigate UPI activity and know what to do next.
        </p>
        <div className="hero-actions">
          <Link to="/check" className="button primary-link">Check a payment</Link>
          <Link to={user ? "/transactions" : "/simulator"} className="button ghost-link">Explore fraud protection</Link>
        </div>
        <p className="note">Lost money just now? <Link to="/emergency">Go to emergency steps →</Link></p>
      </section>

      <section className="sec">
        <div className="sec-head"><span className="sec-no">How</span><h2>How it works</h2></div>
        <ol className="steps">
          {STEPS.map(([n, t, d]) => (
            <li key={n}><span className="sec-no">{n}</span><h3>{t}</h3><p>{d}</p></li>
          ))}
        </ol>
      </section>

      <section className="sec">
        <div className="sec-head"><span className="sec-no">Scan</span><h2>What you can check</h2></div>
        <ul className="link-grid">
          {SCANS.map(([to, t, d]) => (
            <li key={t}><Link to={to}><strong>{t}</strong><span>{d}</span></Link></li>
          ))}
        </ul>
      </section>

      <section className="sec two-col">
        <div>
          <div className="sec-head"><span className="sec-no">Why</span><h2>Explanations, not verdicts</h2></div>
          <p>
            Every score shows where it came from: points from the model, from rules and from each pattern in your own
            history. The AI investigator only explains evidence the system already produced and cites the transactions it
            used. Nothing here calls a person a criminal: a high score means "high-risk pattern", not proof.
          </p>
          <p className="muted">
            The model learned from PaySim, a synthetic mobile-money dataset, because no public dataset of real UPI fraud
            exists. <Link to="/model">See how it performs →</Link>
          </p>
        </div>
        <div>
          <div className="sec-head"><span className="sec-no">Privacy</span><h2>Privacy first</h2></div>
          <ul className="plain">
            <li>Screenshots are read on your device and never uploaded.</li>
            <li>UPI Guard never asks for your UPI PIN, OTP, card details or bank password.</li>
            <li>OTPs, PINs and card numbers pasted into evidence are masked before saving.</li>
            <li>Export or delete your data any time; set automatic deletion in Settings.</li>
            <li>AI is off until you turn it on.</li>
          </ul>
          <Link to="/privacy">Read the privacy notes →</Link>
        </div>
      </section>

      <section className="sec two-col">
        <div>
          <div className="sec-head"><span className="sec-no">Demo</span><h2>Try it with synthetic data</h2></div>
          <p>
            Run nine scripted scams in the <Link to="/simulator">fraud simulator</Link>: account takeover, fake refunds, KYC
            and QR scams and more. Each event goes through the same engines as a real payment.
            {user ? <> Or load the <Link to="/transactions">demo history</Link> into your account.</> : null}
          </p>
          <p className="synthetic-note">Demo data is synthetic and always labelled. It is not real bank data.</p>
        </div>
        <div>
          <div className="sec-head"><span className="sec-no">Help</span><h2>Emergency assistance</h2></div>
          <p>
            If you've lost money, speed matters: call <b>1930</b>, tell your bank, and file at <b>cybercrime.gov.in</b>.
            UPI Guard can't freeze accounts or recover money; it tells you who can.
          </p>
          <Link to="/emergency">Emergency steps →</Link>
        </div>
      </section>
    </div>
  );
}

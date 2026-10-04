import { useEffect, useState } from "react";
import { Link } from "react-router";
import { getGuidance } from "../lib/api.js";

// Static fallback so this page works even if the API is down.
export const FALLBACK = {
  steps: [
    { title: "Stop further payments", text: "Don't approve any more requests or scan any QR. Block UPI in your bank app or by calling your bank." },
    { title: "Preserve the evidence", text: "Keep screenshots, the transaction ID / UTR, the scammer's UPI ID, number, messages and links." },
    { title: "Contact your bank", text: "Call the number on the back of your card or in the official app and report the transaction." },
    { title: "Report the fraud", text: "Call 1930 and file a complaint on cybercrime.gov.in. Keep the acknowledgement number." },
    { title: "Secure your accounts", text: "Change your UPI PIN and passwords, remove unknown devices, uninstall screen-sharing apps." },
  ],
  resources: [
    { name: "National Cyber Crime Helpline", contact: "1930", url: "tel:1930", when: "You have lost money." },
    { name: "National Cyber Crime Reporting Portal", contact: "cybercrime.gov.in", url: "https://cybercrime.gov.in", when: "File a complaint." },
  ],
};

export default function Emergency() {
  const [g, setG] = useState(FALLBACK);
  useEffect(() => { getGuidance().then(setG).catch(() => {}); }, []);
  return (
    <div className="emergency">
      <p className="label">Emergency</p>
      <h1 className="emergency-title">Possible fraud? Act now.</h1>
      <p className="lede">The first hours matter most. Fast reports give banks and police the best chance of freezing the money.</p>
      <a className="call-1930" href="tel:1930">Call 1930 <span>National Cyber Crime Helpline</span></a>

      <ol className="emergency-steps">
        {g.steps.map((s, i) => (
          <li key={s.title}><span className="step-no">{i + 1}</span><div><h2>{s.title}</h2><p>{s.text}</p></div></li>
        ))}
      </ol>

      <h2 className="sub-title">Official channels</h2>
      <ul className="resource-list">
        {g.resources.map((r) => (
          <li key={r.name}>
            <a href={r.url} target={r.url.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer"><b>{r.name}</b> · {r.contact}</a>
            <p>{r.when}</p>
          </li>
        ))}
      </ul>

      <div className="callout">
        UPI Guard can't block accounts, freeze money or file complaints for you; only your bank and the authorities can.
        It can help you <Link to="/cases">collect the evidence</Link> and <Link to="/cases">generate an incident report</Link> to share with them.
        Never share your UPI PIN or OTP with anyone who calls to "help" you recover money: recovery scams are common.
      </div>
    </div>
  );
}

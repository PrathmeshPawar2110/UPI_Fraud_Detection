import { Link } from "react-router";

// Plain-language results for people who aren't technical. Colour is never the only signal:
// every verdict has an icon and a short headline.
const ICON = { low: "✓", medium: "!", high: "✕", unknown: "?" };

export const PLAIN = {
  received: {
    low: ["Looks OK", "Nothing suspicious found. Still, always confirm the money is in your bank before handing over goods."],
    medium: ["Be careful", "Some warning signs. Do not hand over goods or return any money until the payment shows in your own bank app or bank SMS."],
    high: ["Do not trust this payment", "This matches a common scam. Do not hand over goods, do not send any money back, and do not enter your UPI PIN."],
  },
  sent: {
    low: ["Looks OK", "This looks like a normal payment."],
    medium: ["Be careful", "Some signs match fraud. If you didn't make this payment, call your bank now."],
    high: ["Likely fraud", "This matches account-takeover fraud. If you didn't make this payment, call 1930 and your bank immediately."],
  },
  check: {
    low: ["Looks OK", "No warning signs found. Check the name shown in your UPI app before you pay."],
    medium: ["Be careful", "Some warning signs. Don't pay or share anything until you've confirmed who this really is."],
    high: ["Do not pay", "Strong warning signs of a scam. Don't pay, don't scan, and never share your PIN or OTP."],
    unknown: ["Can't tell", "We couldn't find clear warning signs, but we can't confirm this is safe. Use your bank's official app instead."],
  },
};

export default function Verdict({ level = "unknown", kind = "check", title, text, reasons, children }) {
  const l = PLAIN[kind]?.[level] ? level : "unknown";
  const [head, body] = PLAIN[kind]?.[l] || PLAIN.check.unknown;
  return (
    <section className={"verdict-card " + l} aria-live="polite">
      <div className="verdict-top">
        <span className="verdict-icon" aria-hidden="true">{ICON[l]}</span>
        <div>
          <h2 className="verdict-title">{title || head}</h2>
          <p className="verdict-text">{text || body}</p>
        </div>
      </div>
      {reasons?.length > 0 && (
        <div className="verdict-reasons">
          <p className="verdict-sub">Why:</p>
          <ul>{reasons.slice(0, 4).map((r, i) => <li key={i}>{typeof r === "string" ? r : r.text}</li>)}</ul>
        </div>
      )}
      {children}
      {l === "high" && (
        <div className="verdict-help">
          <a className="big-btn danger-btn" href="tel:1930">Call 1930 (cyber crime helpline)</a>
          <Link className="big-btn ghost-btn" to="/help">What should I do?</Link>
        </div>
      )}
    </section>
  );
}

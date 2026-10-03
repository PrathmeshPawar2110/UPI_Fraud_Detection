import { useEffect, useRef } from "react";

const VERDICTS = {
  low: ["Low risk", "Looks normal", "This transaction matches the pattern of ordinary payments."],
  medium: ["Medium risk", "Worth a second look", "Some signs match known fraud patterns. Confirm you made this payment and know the receiver."],
  high: ["High risk", "Likely fraud", "This transaction closely matches account-takeover fraud: money moved out fast, often emptying the account."],
};
const RECEIVED_VERDICTS = {
  low: ["Low risk", "Looks fine", "You know the sender and the money is in your account."],
  medium: ["Medium risk", "Be careful with this money", "Unexpected money can be a setup. Do not send any of it back or pay anything until you know where it came from."],
  high: ["High risk", "Likely a scam", "This matches a known scam that starts with money arriving in your account, or with a screenshot that says it did."],
};
const BANDS = ["low", "medium", "high"];

function SentAdvice() {
  return (
    <ul>
      <li>Block UPI on your account from your bank app or by calling your bank.</li>
      <li>Call the National Cyber Crime Helpline <b>1930</b> within the first hours. Fast reporting improves the chance of freezing the money.</li>
      <li>File a complaint at <b>cybercrime.gov.in</b> with the transaction ID / UTR.</li>
      <li>Never share your UPI PIN or OTP. You never need a PIN to <i>receive</i> money.</li>
    </ul>
  );
}

function ReceivedAdvice() {
  return (
    <ul>
      <li>Do not send money back to whoever contacts you. A genuine wrong transfer is reversed by the sender's bank: ask them to raise it there.</li>
      <li>Never enter your UPI PIN or approve a collect request to "receive" money.</li>
      <li>Do not hand over goods or services until the credit shows in your bank app or SMS.</li>
      <li>Tell your bank and report at <b>1930</b> or <b>cybercrime.gov.in</b>, so your account is not treated as a mule account.</li>
    </ul>
  );
}

function Line({ k, v }) {
  return (
    <div>
      <dt>{k}</dt>
      <span className="leader" aria-hidden="true" />
      <dd>{v}</dd>
    </div>
  );
}

export default function ResultCard({ result }) {
  const ref = useRef(null);

  useEffect(() => {
    if (result && window.innerWidth < 900) ref.current?.scrollIntoView({ behavior: "smooth" });
  }, [result]);

  return (
    <section className="slip" ref={ref} aria-live="polite">
      <div className="slip-head">
        <span className="label">03 · Risk check</span>
        <span className="label">{result ? result.checkedAt : "Awaiting details"}</span>
      </div>
      {result ? <Result r={result} /> : (
        <div className="slip-empty">
          <dl className="lines">
            <Line k="Fraud score" v="—" />
            <Line k="Risk level" v="—" />
            <Line k="Reasons" v="—" />
          </dl>
          <p>Enter the payment details and press <b>Check this transaction</b>. The verdict appears here.</p>
        </div>
      )}
    </section>
  );
}

function Result({ r }) {
  const [band, title, text] = (r.received ? RECEIVED_VERDICTS : VERDICTS)[r.risk];
  const refs = [
    ["Transaction ID", r.refs.txnId],
    [r.received ? "Received from" : "Paid to", r.refs.payee],
    ["UPI ID", r.refs.payeeUpi],
    ["Status", r.refs.status],
    ["Receiver balances", !r.received && (r.used_receiver_balances ? "used" : "not provided")],
  ].filter(([, v]) => v);

  return (
    <div className={r.risk}>
      <div className="verdict">
        <span className="stamp">{band}</span>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>

      <div className="score">
        {r.probability == null ? (<>
          <span className="label">Checked with</span>
          <b className="rules">Scam rules</b>
        </>) : (<>
          <span className="label">Fraud score</span>
          <b>{(r.probability * 100).toFixed(r.probability < 0.01 ? 2 : 1)}%</b>
        </>)}
      </div>
      <div className="scale" aria-hidden="true">
        {BANDS.map((b) => <span key={b} className={b === r.risk ? "on " + b : undefined} />)}
        <i style={{ left: r.meter * 100 + "%" }} />
      </div>
      <div className="scale-labels label" aria-hidden="true"><span>Low</span><span>Medium</span><span>High</span></div>

      <h4 className="label">{r.method === "rules" ? "Why" : "Why the model thinks so"}</h4>
      <ul className="reasons">
        {r.reasons.map((x) => (
          <li key={x.text} className={x.direction}>
            <span className="dot" aria-hidden="true">{x.direction === "up" ? "▲" : "▼"}</span>
            <span><span className="sr-only">{x.direction === "up" ? "Raises risk: " : "Lowers risk: "}</span>{x.text}</span>
          </li>
        ))}
      </ul>

      {r.risk !== "low" && (
        <div className={"advice " + r.risk}>
          <strong>{r.received ? "What to do" : "If you did not make or expect this payment"}</strong>
          {r.received ? <ReceivedAdvice /> : <SentAdvice />}
        </div>
      )}

      <dl className="lines refs">
        {refs.map(([k, v]) => <Line key={k} k={k} v={v} />)}
      </dl>
    </div>
  );
}

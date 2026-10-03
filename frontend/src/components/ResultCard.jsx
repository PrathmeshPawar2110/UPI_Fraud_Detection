import { useEffect, useRef } from "react";

const VERDICTS = {
  low: ["Looks normal", "This transaction matches the pattern of ordinary payments."],
  medium: ["Worth a second look", "Some signs match known fraud patterns. Confirm you made this payment and know the receiver."],
  high: ["High fraud risk", "This transaction closely matches account-takeover fraud: money moved out fast, often emptying the account."],
};

export default function ResultCard({ result }) {
  const ref = useRef(null);

  useEffect(() => {
    if (result && window.innerWidth < 860) ref.current?.scrollIntoView({ behavior: "smooth" });
  }, [result]);

  return (
    <section className="card" ref={ref}>
      <h2><span className="step">3</span> Result</h2>
      {result ? <Result r={result} /> : (
        <div className="result-empty">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" />
            <path d="M9 12l2 2 4-4" />
          </svg>
          <div>Your risk check will appear here.</div>
        </div>
      )}
    </section>
  );
}

function Result({ r }) {
  const [title, text] = VERDICTS[r.risk];
  const refs = [
    ["Transaction ID", r.refs.txnId],
    ["Paid to", r.refs.payee],
    ["UPI ID", r.refs.payeeUpi],
    ["Status", r.refs.status],
    ["Receiver balances", r.used_receiver_balances ? "used" : "not provided (scored without them)"],
  ].filter(([, v]) => v);

  return (
    <div>
      <div className={"verdict " + r.risk}>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
      <div className="score">
        Fraud score <b>{(r.probability * 100).toFixed(r.probability < 0.01 ? 2 : 1)}%</b>
      </div>
      <div className="meter">
        <div className="meter-bar"><div className="meter-pin" style={{ left: r.meter * 100 + "%" }} /></div>
        <div className="meter-labels"><span>Low risk</span><span>Medium</span><span>High risk</span></div>
      </div>

      <h4>Why the model thinks so</h4>
      <ul className="reasons">
        {r.reasons.map((x) => (
          <li key={x.text} className={x.direction}>
            <span className="dot">{x.direction === "up" ? "↑" : "↓"}</span>
            <span>{x.text}</span>
          </li>
        ))}
      </ul>

      {r.risk !== "low" && (
        <>
          <h4>What to do</h4>
          <div className="advice">
            If you did not make or expect this payment:
            <ul>
              <li>Block UPI on your account from your bank app or by calling your bank.</li>
              <li>Call the National Cyber Crime Helpline <b>1930</b> within the first hours. Fast reporting improves the chance of freezing the money.</li>
              <li>File a complaint at <b>cybercrime.gov.in</b> with the transaction ID / UTR.</li>
              <li>Never share your UPI PIN or OTP. You never need a PIN to <i>receive</i> money.</li>
            </ul>
          </div>
        </>
      )}

      <dl className="ref">
        {refs.map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

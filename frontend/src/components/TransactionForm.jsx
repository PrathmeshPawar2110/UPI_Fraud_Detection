import { inr } from "../lib/format.js";

function Input({ name, form, filled, onChange, money, ...rest }) {
  const input = (
    <input
      id={name}
      className={filled.has(name) ? "filled" : undefined}
      value={form[name]}
      onChange={(e) => onChange(name, e.target.value)}
      {...rest}
    />
  );
  return money ? <div className="money">{input}</div> : input;
}

const TYPES = [
  ["TRANSFER", "Sent money", "To a person or UPI ID"],
  ["CASH_OUT", "Cash withdrawal", "ATM, agent or cash-out"],
  ["RECEIVED", "Received money", "Credited to your account"],
];

const QUESTIONS = [
  ["knowsSender", "Do you know the sender, and were you expecting this money?"],
  ["inBank", "Does the money show in your bank app or bank SMS (not just the screenshot)?"],
  ["askedToPay", "Has anyone asked you to send it back, refund it, or pay a fee or deposit?"],
];

function Question({ name, text, value, onChange }) {
  return (
    <fieldset className="question">
      <legend>{text}</legend>
      <div className="pills">
        {[["yes", "Yes"], ["no", "No"], ["unsure", "Not sure"]].map(([v, label]) => (
          <label key={v}>
            <input type="radio" name={name} value={v} checked={value === v} onChange={() => onChange(name, v)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function TransactionForm({
  form, filled, onChange, destOpen, onDestToggle, refOpen, onRefToggle, onSubmit, busy, error, balBeforeRef,
}) {
  const field = { form, filled, onChange };
  const received = form.type === "RECEIVED";
  const a = parseFloat(form.amount), b = parseFloat(form.balBefore);
  const afterHint = Number.isFinite(a) && Number.isFinite(b) && !form.balAfter
    ? `Will use ${inr(Math.max(b - a, 0))} (balance before − amount).`
    : "Leave blank to use balance before minus amount.";

  const submit = (e) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <form className="sec" noValidate onSubmit={submit}>
      <div className="sec-head">
        <span className="sec-no">02</span>
        <h2>Transaction details</h2>
      </div>
      <p className="sub">Fields read from your screenshot are outlined in green. Fill in anything that is missing.</p>

      <div className="field">
        <label id="typeLabel">What kind of payment was it?</label>
        <div className="seg" role="radiogroup" aria-labelledby="typeLabel">
          {TYPES.map(([value, title, hint]) => (
            <div key={value} className="seg-opt">
              <input type="radio" name="type" id={"t" + value} value={value}
                     checked={form.type === value} onChange={() => onChange("type", value)} />
              <label htmlFor={"t" + value}>{title}<small>{hint}</small></label>
            </div>
          ))}
        </div>
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="amount">Amount</label>
          <Input {...field} money name="amount" type="number" min="1" step="0.01" placeholder="e.g. 5000" required />
        </div>
        <div className="field">
          <label htmlFor="when">Date and time</label>
          <Input {...field} name="when" type="datetime-local" required />
        </div>
      </div>

      {received ? (
        <div className="questions">
          <p className="note">
            The model only learned fraud on money going <i>out</i>, so received money is checked against common
            incoming-money scams instead.
          </p>
          {QUESTIONS.map(([name, text]) => (
            <Question key={name} name={name} text={text} value={form[name]} onChange={onChange} />
          ))}
        </div>
      ) : (<>
      <div className="row">
        <div className="field">
          <label htmlFor="balBefore">Sender's balance before <span className="hint">(check your bank SMS)</span></label>
          <Input {...field} money name="balBefore" type="number" min="0" step="0.01" placeholder="e.g. 42000" required
                 ref={balBeforeRef} />
        </div>
        <div className="field">
          <label htmlFor="balAfter">Sender's balance after</label>
          <Input {...field} money name="balAfter" type="number" min="0" step="0.01" placeholder="Auto: before − amount" />
          <p className="note">{afterHint}</p>
        </div>
      </div>

      <details open={destOpen} onToggle={(e) => onDestToggle(e.currentTarget.open)}>
        <summary>Receiver's account balance <span>Optional, only if you know it</span></summary>
        <div className="row">
          <div className="field">
            <label htmlFor="destBefore">Receiver's balance before</label>
            <Input {...field} money name="destBefore" type="number" min="0" step="0.01" />
          </div>
          <div className="field">
            <label htmlFor="destAfter">Receiver's balance after</label>
            <Input {...field} money name="destAfter" type="number" min="0" step="0.01" />
          </div>
        </div>
        <p className="note" style={{ marginTop: -6 }}>Usually only a bank can see this. The check works without it.</p>
      </details>
      </>)}

      <details open={refOpen} onToggle={(e) => onRefToggle(e.currentTarget.open)}>
        <summary>Reference details <span>Kept for your record, not scored</span></summary>
        <div className="row">
          <div className="field"><label htmlFor="txnId">Transaction ID / UTR</label><Input {...field} name="txnId" type="text" /></div>
          <div className="field"><label htmlFor="payee">{received ? "Received from" : "Paid to"}</label><Input {...field} name="payee" type="text" /></div>
        </div>
        <div className="row">
          <div className="field"><label htmlFor="payeeUpi">{received ? "Sender's UPI ID" : "Receiver's UPI ID"}</label><Input {...field} name="payeeUpi" type="text" placeholder="name@bank" /></div>
          <div className="field"><label htmlFor="status">Status</label><Input {...field} name="status" type="text" /></div>
        </div>
      </details>

      <button className="primary" type="submit" disabled={busy}>{busy ? "Checking…" : "Check this transaction"}</button>
      <div className="error" role="alert">{error}</div>
    </form>
  );
}

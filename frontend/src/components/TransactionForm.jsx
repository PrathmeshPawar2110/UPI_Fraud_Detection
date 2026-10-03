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

export default function TransactionForm({
  form, filled, onChange, destOpen, onDestToggle, refOpen, onRefToggle, onSubmit, busy, error, balBeforeRef,
}) {
  const field = { form, filled, onChange };
  const a = parseFloat(form.amount), b = parseFloat(form.balBefore);
  const afterHint = Number.isFinite(a) && Number.isFinite(b) && !form.balAfter
    ? `Will use ${inr(Math.max(b - a, 0))} (balance before − amount).`
    : "Leave blank to use balance before minus amount.";

  const submit = (e) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <form className="card" noValidate onSubmit={submit}>
      <h2><span className="step">2</span> Check the transaction details</h2>
      <p className="sub">Fields filled from your screenshot are highlighted green. Fill in anything that is missing.</p>

      <div className="field">
        <label>What kind of payment was it?</label>
        <div className="seg">
          <input type="radio" name="type" id="tTransfer" value="TRANSFER"
                 checked={form.type === "TRANSFER"} onChange={() => onChange("type", "TRANSFER")} />
          <label htmlFor="tTransfer">Sent money<small>To a person or UPI ID</small></label>
          <input type="radio" name="type" id="tCashout" value="CASH_OUT"
                 checked={form.type === "CASH_OUT"} onChange={() => onChange("type", "CASH_OUT")} />
          <label htmlFor="tCashout">Cash withdrawal<small>ATM, agent or cash-out</small></label>
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
        <summary>Receiver's account balance <span>— optional, only if you know it</span></summary>
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

      <details open={refOpen} onToggle={(e) => onRefToggle(e.currentTarget.open)}>
        <summary>Reference details <span>— from the screenshot, kept for your record</span></summary>
        <div className="row">
          <div className="field"><label htmlFor="txnId">Transaction ID / UTR</label><Input {...field} name="txnId" type="text" /></div>
          <div className="field"><label htmlFor="payee">Paid to</label><Input {...field} name="payee" type="text" /></div>
        </div>
        <div className="row">
          <div className="field"><label htmlFor="payeeUpi">Receiver's UPI ID</label><Input {...field} name="payeeUpi" type="text" placeholder="name@bank" /></div>
          <div className="field"><label htmlFor="status">Status</label><Input {...field} name="status" type="text" /></div>
        </div>
      </details>

      <button className="primary" type="submit" disabled={busy}>{busy ? "Checking…" : "Check this transaction"}</button>
      <div className="error">{error}</div>
    </form>
  );
}

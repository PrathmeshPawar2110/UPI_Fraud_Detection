import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import UploadCard from "../components/UploadCard.jsx";
import TransactionForm from "../components/TransactionForm.jsx";
import ResultCard from "../components/ResultCard.jsx";
import ModelInfo from "../components/ModelInfo.jsx";
import { checkReceived, createTransaction, getModelInfo, predict } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { localDateTime } from "../lib/format.js";

const EMPTY_FORM = {
  type: "TRANSFER",
  amount: "",
  when: "",
  balBefore: "",
  balAfter: "",
  destBefore: "",
  destAfter: "",
  txnId: "",
  payee: "",
  payeeUpi: "",
  status: "",
  // received money only: "yes" | "no" | "unsure"
  knowsSender: "",
  inBank: "",
  askedToPay: "",
};

const num = (v) => (String(v).trim() === "" ? null : Number(v));
const DIRECTION = { TRANSFER: "sent", CASH_OUT: "cash_out", RECEIVED: "received" };
const STATUS = { Successful: "success", Failed: "failed", Pending: "pending" };

export default function Check() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(() => ({ ...EMPTY_FORM, when: localDateTime() }));
  const [filled, setFilled] = useState(() => new Set()); // fields filled from the screenshot
  const [app, setApp] = useState(null);                  // payment app detected by OCR
  const [destOpen, setDestOpen] = useState(false);
  const [refOpen, setRefOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [checked, setChecked] = useState(null); // form values behind the current result
  const [modelInfo, setModelInfo] = useState(null);
  const [modelInfoFailed, setModelInfoFailed] = useState(false);
  const balBeforeRef = useRef(null);

  useEffect(() => {
    getModelInfo().then(setModelInfo).catch(() => setModelInfoFailed(true));
  }, []);

  const changeField = (key, value) => {
    setForm((f) => ({ ...f, [key]: value }));
    setFilled((s) => {
      if (!s.has(key)) return s;
      const next = new Set(s);
      next.delete(key);
      return next;
    });
  };

  // Fill the form from OCR output; returns what was found / missing for the status chips.
  const applyParsed = useCallback((p) => {
    const updates = {};
    const put = (key, value) => {
      if (value === null || value === undefined || value === "") return false;
      updates[key] = String(value);
      return true;
    };
    const found = [], missing = [];
    const mark = (ok, label) => (ok ? found : missing).push(label);

    const received = p.direction === "received";
    if (p.direction) {
      // a cash withdrawal the user already picked stays; otherwise follow the screenshot
      updates.type = received ? "RECEIVED" : "TRANSFER";
      found.push(received ? "Money received" : "Money sent");
    }
    mark(put("amount", p.amount), "Amount");
    if (p.date || p.time) {
      const now = new Date();
      const d = p.date ? new Date(p.date.y, p.date.mo, p.date.d) : now;
      const t = p.time || { h: 12, min: 0 };
      put("when", localDateTime(d, t.h, t.min));
    }
    mark(!!p.time, "Time");
    const refs = [put("txnId", p.txnId), put("payee", p.payee), put("payeeUpi", p.payeeUpi), put("status", p.status)];
    mark(refs[0], "Transaction ID");
    mark(refs[1] || refs[2], received ? "Sender" : "Payee");
    if (refs.some(Boolean)) setRefOpen(true);
    missing.push(received ? "3 quick questions" : "Balance before");
    setApp(p.app || null);

    setForm((f) => {
      const keepCashOut = f.type === "CASH_OUT" && updates.type === "TRANSFER";
      return { ...f, ...updates, ...(keepCashOut ? { type: "CASH_OUT" } : {}) };
    });
    setFilled(new Set(Object.keys(updates).filter((k) => k !== "type")));
    if (!received) balBeforeRef.current?.focus();
    return { found, missing };
  }, []);

  async function check(values) {
    setError("");
    const received = values.type === "RECEIVED";
    const amount = num(values.amount), balBefore = num(values.balBefore);
    if (!amount || amount <= 0) return setError("Please enter the amount.");
    if (!values.when) return setError("Please enter the date and time.");
    const hour = new Date(values.when).getHours();
    const destBefore = num(values.destBefore), destAfter = num(values.destAfter);
    if (received) {
      if (!values.knowsSender || !values.inBank || !values.askedToPay) return setError("Please answer the three questions.");
    } else {
      if (balBefore === null) return setError("Please enter the sender's balance before the payment.");
      if ((destBefore === null) !== (destAfter === null)) return setError("Enter both receiver balances, or leave both empty.");
    }

    setBusy(true);
    try {
      const r = received
        ? await checkReceived({
          amount, hour, knows_sender: values.knowsSender, in_bank: values.inBank, asked_to_pay: values.askedToPay,
        })
        : await predict({
          type: values.type,
          amount,
          hour,
          sender_balance_before: balBefore,
          sender_balance_after: num(values.balAfter),
          receiver_balance_before: destBefore,
          receiver_balance_after: destAfter,
        });
      const checkedAt = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
      setResult({
        ...r, checkedAt, received,
        refs: { txnId: values.txnId, payee: values.payee, payeeUpi: values.payeeUpi, status: values.status },
      });
      setChecked(values);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  // Store the checked transaction and open its investigation (scored against the user's history).
  async function saveAndInvestigate() {
    const v = checked;
    setSaving(true);
    setError("");
    try {
      const received = v.type === "RECEIVED";
      const tx = await createTransaction({
        occurred_at: v.when,
        direction: DIRECTION[v.type],
        amount: num(v.amount),
        counterparty_name: v.payee || null,
        // masked IDs from receipts ("••••0259@ptsbi") aren't full UPI IDs, so they're kept as the name only
        counterparty_upi: v.payeeUpi.includes("@") && !v.payeeUpi.startsWith("•") ? v.payeeUpi : null,
        external_id: /^[A-Za-z0-9-]{4,64}$/.test(v.txnId) ? v.txnId : null,
        status: STATUS[v.status] || "success",
        payment_app: app,
        balance_before: received ? null : num(v.balBefore),
        balance_after: received ? null : num(v.balAfter),
        receiver_balance_before: received ? null : num(v.destBefore),
        receiver_balance_after: received ? null : num(v.destAfter),
        received_answers: received ? { knows_sender: v.knowsSender, in_bank: v.inBank, asked_to_pay: v.askedToPay } : null,
        source: filled.size ? "screenshot" : "manual",
      });
      window.dispatchEvent(new Event("upig:alerts"));
      navigate(`/investigate/${tx.id}`);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  function loadSample(kind) {
    if (!modelInfo) return;
    const list = modelInfo.samples[kind];
    const s = list[Math.floor(Math.random() * list.length)];
    const values = {
      ...EMPTY_FORM,
      type: s.type,
      amount: String(s.amount),
      when: localDateTime(new Date(), s.step % 24, Math.floor(Math.random() * 60)),
      balBefore: String(s.oldbalanceOrg),
      balAfter: String(s.newbalanceOrig),
      destBefore: String(s.oldbalanceDest),
      destAfter: String(s.newbalanceDest),
    };
    setForm(values);
    setFilled(new Set());
    setDestOpen(true);
    check(values);
  }

  return (
    <>
      <header className="masthead">
        <div>
          <p className="label">Check · screenshot or details</p>
          <h1>Check a <em>payment</em></h1>
          <p className="lede">
            Upload a payment screenshot or type the details. The model scores how closely the payment matches
            account-takeover fraud, and says why. <Link to="/before-you-pay">Scan a message, link, QR or UPI ID →</Link>
          </p>
        </div>
        <div className="samples">
          <span className="label">Or try</span>
          <button className="textbtn" type="button" onClick={() => loadSample("legit")}>a normal payment <span>→</span></button>
          <button className="textbtn" type="button" onClick={() => loadSample("fraud")}>a suspicious payment <span>→</span></button>
        </div>
      </header>

      <div className="layout">
        <div>
          <UploadCard onParsed={applyParsed} />
          <TransactionForm
            form={form}
            filled={filled}
            onChange={changeField}
            destOpen={destOpen}
            onDestToggle={setDestOpen}
            refOpen={refOpen}
            onRefToggle={setRefOpen}
            onSubmit={() => check(form)}
            busy={busy}
            error={error}
            balBeforeRef={balBeforeRef}
          />
        </div>
        <aside>
          <ResultCard result={result} />
          {result && (
            <div className="save-panel">
              {user ? (
                <>
                  <button type="button" className="primary" disabled={saving} onClick={saveAndInvestigate}>
                    {saving ? "Saving…" : "Save & investigate"}
                  </button>
                  <p className="note">Adds it to your history and re-scores it against your past payments (new recipient,
                    unusual amount, rapid transfers…).</p>
                </>
              ) : (
                <p className="note"><Link to="/login?next=/check">Sign in</Link> to save this payment, compare it with your
                  history and open an investigation.</p>
              )}
            </div>
          )}
        </aside>
      </div>

      <ModelInfo info={modelInfo} failed={modelInfoFailed} />
    </>
  );
}

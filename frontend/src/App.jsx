import { useCallback, useEffect, useRef, useState } from "react";
import UploadCard from "./components/UploadCard.jsx";
import TransactionForm from "./components/TransactionForm.jsx";
import ResultCard from "./components/ResultCard.jsx";
import ModelInfo from "./components/ModelInfo.jsx";
import { getModelInfo, predict } from "./lib/api.js";
import { localDateTime } from "./lib/format.js";

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
};

const num = (v) => (String(v).trim() === "" ? null : Number(v));

export default function App() {
  const [form, setForm] = useState(() => ({ ...EMPTY_FORM, when: localDateTime() }));
  const [filled, setFilled] = useState(() => new Set()); // fields filled from the screenshot
  const [destOpen, setDestOpen] = useState(false);
  const [refOpen, setRefOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
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
    mark(refs[1] || refs[2], "Payee");
    if (refs.some(Boolean)) setRefOpen(true);
    missing.push("Balance before");

    setForm((f) => ({ ...f, ...updates }));
    setFilled(new Set(Object.keys(updates)));
    balBeforeRef.current?.focus();
    return { found, missing };
  }, []);

  async function check(values) {
    setError("");
    const amount = num(values.amount), balBefore = num(values.balBefore);
    if (!amount || amount <= 0) return setError("Please enter the amount.");
    if (balBefore === null) return setError("Please enter the sender's balance before the payment.");
    if (!values.when) return setError("Please enter the date and time.");
    const destBefore = num(values.destBefore), destAfter = num(values.destAfter);
    if ((destBefore === null) !== (destAfter === null)) return setError("Enter both receiver balances, or leave both empty.");

    setBusy(true);
    try {
      const r = await predict({
        type: values.type,
        amount,
        hour: new Date(values.when).getHours(),
        sender_balance_before: balBefore,
        sender_balance_after: num(values.balAfter),
        receiver_balance_before: destBefore,
        receiver_balance_after: destAfter,
      });
      setResult({ ...r, refs: { txnId: values.txnId, payee: values.payee, payeeUpi: values.payeeUpi, status: values.status } });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
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
    <div className="wrap">
      <header>
        <div className="logo">
          <div className="logo-mark">₹</div>
          <div>
            <h1>UPI Fraud Check</h1>
            <p>Upload a payment screenshot or enter the details to see how risky a transaction looks.</p>
          </div>
        </div>
        <div className="samples">
          <button className="ghost" type="button" onClick={() => loadSample("legit")}>Try a normal example</button>
          <button className="ghost" type="button" onClick={() => loadSample("fraud")}>Try a suspicious example</button>
        </div>
      </header>

      <div className="grid">
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
        <div>
          <ResultCard result={result} />
          <ModelInfo info={modelInfo} failed={modelInfoFailed} />
        </div>
      </div>

      <footer>
        Educational project. The model is trained on PaySim, a synthetic mobile-money dataset, because no public dataset of
        real UPI fraud exists. It is not financial advice. If you think you were defrauded, call the National Cyber Crime
        Helpline <b>1930</b> or report at cybercrime.gov.in.
      </footer>
    </div>
  );
}

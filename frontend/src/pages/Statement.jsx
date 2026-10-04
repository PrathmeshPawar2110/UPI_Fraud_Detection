import { useState } from "react";
import { Link } from "react-router";
import Verdict from "../components/Verdict.jsx";
import { ErrorNote, TxRow } from "../components/ui.jsx";
import { importFile } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";

const MAX_BYTES = 4_000_000;
const ACCEPT = ".csv,.xlsx,.xls,.txt,.tsv,text/csv,text/plain,application/vnd.ms-excel," +
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const EXAMPLE = "Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance\n" +
  "01/09/2026 10:05,UPI-CHAI POINT-chaipoint.ka@ybl-412345678901,240,,41760\n" +
  "01/09/2026 19:40,UPI-FRESH MART-freshmart.blr@okaxis-412345678902,1200,,40560\n" +
  "02/09/2026 09:00,NEFT-EMPLOYER PAYROLL,,62000,102560\n" +
  "03/09/2026 02:10,UPI-QUICK PAY-quickpay.mule01@axl-412345678903,102560,,0\n";

const WHERE = [
  ["Bank app or net banking", "Open Account statement, choose the dates, and download as Excel (.xls / .xlsx) or CSV."],
  ["Paytm", "Balance & History → Download statement → Excel."],
  ["PhonePe / Google Pay", "These only give PDF statements. Download the statement from your bank instead."],
];

export default function Statement() {
  const { user } = useAuth();
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function scan(f) {
    setError(null);
    setResult(null);
    if (/\.pdf$/i.test(f.name) || f.type === "application/pdf") {
      return setError(new Error("PDF statements can't be read yet. Download the statement as Excel or CSV from your bank instead."));
    }
    if (f.size > MAX_BYTES) return setError(new Error("That file is too large (max 4 MB). Choose fewer months and try again."));
    setFile(f);
    setBusy(true);
    try {
      setResult(await importFile(f));
      window.dispatchEvent(new Event("upig:alerts"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const reset = () => { setFile(null); setResult(null); setError(null); };

  if (!user) {
    return (
      <div className="guided">
        <h1 className="guided-title">Scan my statement</h1>
        <p className="lede">Upload your bank or UPI statement (Excel or CSV) and we'll check every payment in it for fraud.</p>
        <p>You need a free account, so the payments can be saved and compared with each other.</p>
        <div className="result-actions">
          <Link className="big-btn primary-btn" to="/login?mode=signup&next=/statement">Create free account</Link>
          <Link className="big-btn ghost-btn" to="/login?next=/statement">Sign in</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="guided">
      <ol className="stepper" aria-label="Steps">
        <li className={result ? "done" : "on"}><span>{result ? "✓" : 1}</span>Upload</li>
        <li className={result ? "on" : ""}><span>2</span>Result</li>
      </ol>
      <h1 className="guided-title">Scan my statement</h1>

      {!result && (
        <>
          <p className="lede">Upload your bank or UPI statement and we'll check every payment in it.</p>
          <div className="shot-box">
            <label className={"big-btn primary-btn file-btn" + (busy ? " busy" : "")}>
              <input type="file" accept={ACCEPT} disabled={busy}
                     onChange={(e) => { const f = e.target.files[0]; e.target.value = ""; if (f) scan(f); }} />
              {busy ? "Checking payments…" : "Choose statement file"}
            </label>
            <p className="small-print">Excel (.xlsx, .xls) or CSV, up to 4 MB (about 2,000 payments).
              Payments you've already saved are skipped, so it's safe to upload overlapping months.</p>
            {busy && file && <p className="small-print" role="status">Reading {file.name}…</p>}
            {!busy && (
              <button type="button" className="textbtn" onClick={() => scan(new File([EXAMPLE], "example-statement.csv", { type: "text/csv" }))}>
                Try with an example statement
              </button>
            )}
          </div>
          <ErrorNote error={error} />
          <details className="more-details">
            <summary>Where do I get my statement?</summary>
            <ul className="do-list">{WHERE.map(([w, t]) => <li key={w}><b>{w}:</b> {t}</li>)}</ul>
            <p className="small-print">We need a date and an amount for each payment, and either debit / credit columns
              or a sent / received column. Other columns (narration, UPI ID, reference, balance) make the check better.</p>
          </details>
        </>
      )}

      {result && <Result r={result} file={file} onAgain={reset} />}
    </div>
  );
}

function Result({ r, file, onAgain }) {
  const level = r.high_risk > 0 ? "high" : r.medium_risk > 0 ? "medium" : r.imported > 0 ? "low" : "unknown";
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const title = r.high_risk > 0 ? `${plural(r.high_risk, "dangerous payment")} found`
    : r.medium_risk > 0 ? `${plural(r.medium_risk, "payment")} to look at`
    : r.imported > 0 ? "No fraud found" : "Nothing new to check";
  const text = r.high_risk > 0 ? "Open each one below. If you didn't make a payment, call 1930 and your bank now."
    : r.medium_risk > 0 ? "Some payments have warning signs. Open each one and confirm you made it."
    : r.imported > 0 ? "None of the payments in this file matched a fraud pattern."
    : "Every payment in this file was already in My payments.";

  return (
    <>
      <Verdict kind="check" level={level} title={title} text={text}>
        <p className="verdict-details">
          Checked {plural(r.imported, "new payment")} from <b>{file?.name}</b>
          {r.duplicates > 0 && <> · {r.duplicates} already saved, skipped</>}
          {r.errors.length > 0 && <> · {plural(r.errors.length, "row")} couldn't be read</>}
        </p>
      </Verdict>

      {r.flagged.length > 0 && (
        <section>
          <h2 className="verdict-sub">Payments to check</h2>
          <ul className="tx-list">{r.flagged.map((t) => <TxRow key={t.id} t={t} />)}</ul>
          {r.flagged.length < r.high_risk + r.medium_risk && (
            <p className="small-print">Showing the first {r.flagged.length}. See the rest in My payments.</p>
          )}
        </section>
      )}

      {r.errors.length > 0 && (
        <details className="more-details">
          <summary>{plural(r.errors.length, "row")} couldn't be read</summary>
          <ul className="small-print">{r.errors.map((e, i) => <li key={i}>Line {e.line}: {e.error}</li>)}</ul>
        </details>
      )}

      <div className="result-actions">
        <Link className="big-btn ghost-btn" to={r.flagged.length ? "/transactions?risk=high" : "/transactions"}>Open My payments</Link>
        <button type="button" className="big-btn primary-btn" onClick={onAgain}>Scan another file</button>
      </div>
    </>
  );
}

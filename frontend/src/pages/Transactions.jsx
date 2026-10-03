import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ErrorNote, Empty, Loading, PageHead, Synthetic, TxRow } from "../components/ui.jsx";
import { importCsv, listTransactions, loadDemo, removeDemo } from "../lib/api.js";

const FILTERS = { q: "", risk: "", direction: "", app: "", review: "", min_amount: "", max_amount: "",
                  date_from: "", date_to: "", synthetic: "", sort: "newest" };
const PAGE = 50;
const SAMPLE_CSV = "Date,Direction,Amount,Name,UPI ID,Reference,Balance Before\n" +
  "2026-09-01 10:15,sent,450,Chai Point,chaipoint.ka@ybl,512345678901,42000\n" +
  "02/09/2026 19:40,debit,1200,Fresh Mart,freshmart.blr@okaxis,,41550\n";

export default function Transactions() {
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState(() => ({ ...FILTERS, ...Object.fromEntries([...params].filter(([k]) => k in FILTERS)) }));
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [limit, setLimit] = useState(PAGE);
  const [showImport, setShowImport] = useState(params.get("import") === "1");
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    setError(null);
    const q = { ...filters, limit };
    if (q.date_from) q.date_from += "T00:00:00";
    if (q.date_to) q.date_to += "T23:59:59";
    listTransactions(q).then(setData).catch(setError);
  }, [filters, limit]);

  useEffect(() => {
    const t = setTimeout(load, filters.q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, filters.q]);

  const set = (k) => (e) => {
    const next = { ...filters, [k]: e.target.value };
    setFilters(next);
    setLimit(PAGE);
    setParams(Object.fromEntries(Object.entries(next).filter(([key, v]) => v && v !== FILTERS[key])), { replace: true });
  };
  const active = Object.entries(filters).some(([k, v]) => v && v !== FILTERS[k]);

  async function demo(action) {
    setNotice("");
    try {
      if (action === "load") {
        const r = await loadDemo();
        setNotice(`Loaded ${r.loaded} synthetic transactions (${r.high_risk} high risk). ${r.label}.`);
      } else {
        const r = await removeDemo();
        setNotice(`Removed ${r.removed} synthetic transactions.`);
      }
      window.dispatchEvent(new Event("upig:alerts"));
      load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageHead kicker="History" title="Your transactions"
        actions={<>
          <button type="button" className="ghost" onClick={() => setShowImport(!showImport)} aria-expanded={showImport}>Import CSV</button>
          <Link className="button ghost-link" to="/check">Add a payment</Link>
        </>}>
        Every payment is scored against the ones before it. Open one to see why and investigate.
      </PageHead>

      {showImport && <ImportPanel onDone={(msg) => { setNotice(msg); load(); window.dispatchEvent(new Event("upig:alerts")); }} />}
      {notice && <p className="notice" role="status">{notice}</p>}
      <ErrorNote error={error} />

      <form className="filters" onSubmit={(e) => e.preventDefault()} role="search">
        <div className="field grow">
          <label htmlFor="q">Search</label>
          <input id="q" type="text" placeholder="Name, UPI ID, reference or note" value={filters.q} onChange={set("q")} />
        </div>
        <Select id="risk" label="Risk" value={filters.risk} onChange={set("risk")}
                options={[["", "Any"], ["high", "High"], ["medium", "Medium"], ["low", "Low"]]} />
        <Select id="direction" label="Direction" value={filters.direction} onChange={set("direction")}
                options={[["", "Any"], ["sent", "Sent"], ["received", "Received"], ["cash_out", "Cash withdrawal"]]} />
        <Select id="review" label="Status" value={filters.review} onChange={set("review")}
                options={[["", "Any"], ["unreviewed", "Not reviewed"], ["legitimate", "Legitimate"], ["suspicious", "Suspicious"], ["confirmed_fraud", "Confirmed fraud"]]} />
        <Select id="sort" label="Sort" value={filters.sort} onChange={set("sort")}
                options={[["newest", "Newest"], ["oldest", "Oldest"], ["risk", "Highest risk"], ["amount", "Largest amount"]]} />
        <details className="more-filters">
          <summary>More filters</summary>
          <div className="filters-more">
            <div className="field"><label htmlFor="min">Min ₹</label><input id="min" type="number" min="0" value={filters.min_amount} onChange={set("min_amount")} /></div>
            <div className="field"><label htmlFor="max">Max ₹</label><input id="max" type="number" min="0" value={filters.max_amount} onChange={set("max_amount")} /></div>
            <div className="field"><label htmlFor="from">From</label><input id="from" type="date" value={filters.date_from} onChange={set("date_from")} /></div>
            <div className="field"><label htmlFor="to">To</label><input id="to" type="date" value={filters.date_to} onChange={set("date_to")} /></div>
            <div className="field"><label htmlFor="app">App</label><input id="app" type="text" placeholder="e.g. PhonePe" value={filters.app} onChange={set("app")} /></div>
            <Select id="synthetic" label="Data" value={filters.synthetic} onChange={set("synthetic")}
                    options={[["", "All"], ["false", "Real only"], ["true", "Synthetic only"]]} />
          </div>
        </details>
        {active && <button type="button" className="textbtn" onClick={() => { setFilters(FILTERS); setParams({}); }}>Clear filters</button>}
      </form>

      {!data ? <Loading /> : data.total === 0 ? (
        active ? <Empty title="No transactions match these filters." /> : (
          <Empty title="No transactions yet."
                 action={<div className="empty-actions">
                   <Link className="button primary-link" to="/check">Check a payment</Link>
                   <button type="button" className="ghost" onClick={() => setShowImport(true)}>Import a CSV</button>
                   <button type="button" className="ghost" onClick={() => demo("load")}>Load demo data</button>
                 </div>}>
            Check a payment and save it, import a statement as CSV, or load synthetic demo data to explore.
          </Empty>
        )
      ) : (
        <>
          <p className="label count">{data.total} transaction{data.total === 1 ? "" : "s"}</p>
          <ul className="tx-list">{data.items.map((t) => <TxRow key={t.id} t={t} />)}</ul>
          {data.items.length < data.total && (
            <button type="button" className="ghost center" onClick={() => setLimit(limit + PAGE)}>Show more</button>
          )}
        </>
      )}

      <section className="demo-box">
        <p><Synthetic /> Demo dataset: about 90 days of everyday payments with an investment scam, a fake refund and a
          night-time account takeover embedded. Synthetic, not real bank data.</p>
        <div className="empty-actions">
          <button type="button" className="ghost" onClick={() => demo("load")}>Load demo data</button>
          <button type="button" className="textbtn" onClick={() => demo("remove")}>Remove all synthetic data</button>
        </div>
      </section>
    </>
  );
}

function Select({ id, label, value, onChange, options }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={onChange}>
        {options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    </div>
  );
}

function ImportPanel({ onDone }) {
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function pick(e) {
    const f = e.target.files[0];
    if (!f) return;
    if (!/\.(csv|txt)$/i.test(f.name) && !/text|csv/.test(f.type)) return setError(new Error("Please choose a .csv file."));
    if (f.size > 850_000) return setError(new Error("That file is too large (max ~850 KB, about 2,000 rows)."));
    setError(null);
    setName(f.name);
    setText(await f.text());
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await importCsv(text);
      setResult(r);
      onDone(`Imported ${r.imported} transactions (${r.high_risk} high risk).`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2 className="panel-title">Import transactions from CSV</h2>
      <p className="muted">Needs a date/time, a direction (sent/received, or debit/credit) and an amount. Optional: name, UPI ID,
        reference, balance before/after, app, note. Dates like 2026-09-01 10:15 or 01/09/2026 10:15.
        <button type="button" className="textbtn" onClick={() => { setText(SAMPLE_CSV); setName("example.csv"); }}>Use an example</button></p>
      <div className="row">
        <div className="field">
          <label htmlFor="csvfile">CSV file</label>
          <input id="csvfile" type="file" accept=".csv,text/csv,text/plain" onChange={pick} />
        </div>
        <div className="field">
          <label htmlFor="csvtext">…or paste rows</label>
          <textarea id="csvtext" rows={4} value={text} onChange={(e) => { setText(e.target.value); setName(""); }} />
        </div>
      </div>
      {name && <p className="note">Selected: {name}</p>}
      <button type="button" className="primary" disabled={!text.trim() || busy} onClick={submit}>{busy ? "Importing…" : "Import"}</button>
      <ErrorNote error={error} />
      {result?.errors?.length > 0 && (
        <details className="import-errors" open>
          <summary>{result.errors.length} row{result.errors.length > 1 ? "s" : ""} skipped</summary>
          <ul>{result.errors.map((e, i) => <li key={i}>Line {e.line}: {e.error}</li>)}</ul>
        </details>
      )}
    </section>
  );
}

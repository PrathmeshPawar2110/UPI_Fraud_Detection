import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ErrorNote, Empty, Loading, Synthetic, TxRow } from "../components/ui.jsx";
import { listTransactions, loadDemo, removeDemo } from "../lib/api.js";

const FILTERS = { q: "", risk: "", direction: "", app: "", review: "", min_amount: "", max_amount: "",
                  date_from: "", date_to: "", synthetic: "", sort: "newest" };
const PAGE = 50;

export default function Transactions() {
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState(() => ({ ...FILTERS, ...Object.fromEntries([...params].filter(([k]) => k in FILTERS)) }));
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [limit, setLimit] = useState(PAGE);
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
      <div className="list-head">
        <h1 className="guided-title">My payments</h1>
        <div className="list-actions">
          <Link className="big-btn ghost-btn" to="/statement">Upload statement</Link>
          <Link className="big-btn primary-btn" to="/check">+ Check a payment</Link>
        </div>
      </div>
      <p className="lede">Payments you've checked and saved. Tap one to see if it's safe and what to do.</p>
      {notice && <p className="notice" role="status">{notice}</p>}
      <ErrorNote error={error} />

      <form className="filters" onSubmit={(e) => e.preventDefault()} role="search">
        <div className="field grow">
          <label htmlFor="q">Search</label>
          <input id="q" type="text" placeholder="Name, UPI ID or reference" value={filters.q} onChange={set("q")} />
        </div>
        <Select id="risk" label="Show" value={filters.risk} onChange={set("risk")}
                options={[["", "All payments"], ["high", "Only dangerous"], ["medium", "Only 'be careful'"], ["low", "Only OK"]]} />
        <details className="more-filters">
          <summary>More filters</summary>
          <div className="filters-more">
            <Select id="direction" label="Money" value={filters.direction} onChange={set("direction")}
                    options={[["", "In and out"], ["received", "Received"], ["sent", "Sent"], ["cash_out", "Cash withdrawal"]]} />
            <Select id="review" label="Marked as" value={filters.review} onChange={set("review")}
                    options={[["", "Anything"], ["unreviewed", "Not marked"], ["legitimate", "OK"], ["suspicious", "Suspicious"], ["confirmed_fraud", "Fraud"]]} />
            <Select id="sort" label="Order" value={filters.sort} onChange={set("sort")}
                    options={[["newest", "Newest first"], ["oldest", "Oldest first"], ["risk", "Most dangerous first"], ["amount", "Largest first"]]} />
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
          <Empty title="No saved payments yet."
                 action={<div className="empty-actions">
                   <Link className="big-btn primary-btn" to="/check">Check a payment</Link>
                   <Link className="big-btn ghost-btn" to="/statement">Upload a statement</Link>
                 </div>}>
            Check a payment and tap "Save to My payments", or upload your bank statement (Excel or CSV) to check every payment in it.
          </Empty>
        )
      ) : (
        <>
          <p className="label count">{data.total} payment{data.total === 1 ? "" : "s"}</p>
          <ul className="tx-list">{data.items.map((t) => <TxRow key={t.id} t={t} />)}</ul>
          {data.items.length < data.total && (
            <button type="button" className="ghost center" onClick={() => setLimit(limit + PAGE)}>Show more</button>
          )}
        </>
      )}

      <details className="more-details list-more">
        <summary>More options</summary>
        <section className="demo-box">
          <p><Synthetic /> Practice data: about 90 days of everyday payments with a few scams mixed in. Not real bank data.</p>
          <div className="empty-actions">
            <button type="button" className="ghost" onClick={() => demo("load")}>Add practice data</button>
            <button type="button" className="textbtn" onClick={() => demo("remove")}>Remove practice data</button>
          </div>
        </section>
      </details>
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

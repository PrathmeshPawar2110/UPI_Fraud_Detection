import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Empty, ErrorNote, Loading, PageHead } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { inr, when } from "../lib/format.js";

const CATEGORIES = [["account_takeover", "Account takeover"], ["fake_refund", "Fake refund"], ["kyc", "KYC scam"],
  ["wrong_transfer", "Wrong-transfer scam"], ["fake_support", "Fake customer support"], ["investment", "Investment scam"],
  ["qr_scam", "QR scam"], ["phishing", "Phishing link"], ["fake_screenshot", "Fake payment screenshot"],
  ["job_task", "Job / task scam"], ["lottery", "Lottery / prize"], ["digital_arrest", "Digital arrest"], ["other", "Other"]];
const LABEL = Object.fromEntries(CATEGORIES);
const STATUS = { PENDING: "Pending", REVIEWED: "Reviewed", CONFIRMED_BY_USER: "Confirmed by me", DISPUTED: "Disputed", REMOVED: "Withdrawn" };

export default function Reports() {
  const [params] = useSearchParams();
  const [list, setList] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({ entity_type: params.get("vpa") ? "upi" : "upi", entity_value: params.get("vpa") || "",
                                     category: "other", amount: "", incident_date: "", description: "" });
  const [done, setDone] = useState("");

  const load = () => api.listEntityReports().then(setList).catch(setError);
  useEffect(() => { load(); }, []);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    try {
      await api.createEntityReport({ ...form, amount: form.amount ? Number(form.amount) : null,
                                     incident_date: form.incident_date || null, description: form.description || null });
      setDone("Report submitted. Other users only see a count of reports by category, never your details or description.");
      setForm({ ...form, entity_value: "", amount: "", description: "" });
      load();
    } catch (err) { setError(err); }
  }
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <>
      <PageHead kicker="Report" title="Report a suspicious UPI ID, number or link">
        Your report helps warn other UPI Guard users. Reports are <b>unverified</b>: others see only how many people
        reported it and in which category. This is not an official complaint. If you lost money, also report at
        cybercrime.gov.in or call 1930.
      </PageHead>
      <form className="card-form wide" onSubmit={submit}>
        <div className="row">
          <div className="field">
            <label htmlFor="etype">What are you reporting?</label>
            <select id="etype" value={form.entity_type} onChange={set("entity_type")}>
              <option value="upi">UPI ID</option><option value="phone">Phone number</option><option value="url">Website / link</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="evalue">{{ upi: "UPI ID", phone: "Mobile number", url: "Link" }[form.entity_type]}</label>
            <input id="evalue" type="text" maxLength={300} value={form.entity_value} onChange={set("entity_value")} required />
          </div>
        </div>
        <div className="row">
          <div className="field">
            <label htmlFor="cat">Scam type</label>
            <select id="cat" value={form.category} onChange={set("category")}>{CATEGORIES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
          </div>
          <div className="field">
            <label htmlFor="ramount">Amount involved <span className="hint">(optional)</span></label>
            <input id="ramount" type="number" min="1" value={form.amount} onChange={set("amount")} />
          </div>
          <div className="field">
            <label htmlFor="rdate">Date <span className="hint">(optional)</span></label>
            <input id="rdate" type="date" value={form.incident_date} onChange={set("incident_date")} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="rdesc">What happened <span className="hint">(private to you; don't include OTPs, PINs or other people's details)</span></label>
          <textarea id="rdesc" rows={3} maxLength={2000} value={form.description} onChange={set("description")} />
        </div>
        <button type="submit" className="primary small" disabled={!form.entity_value.trim()}>Submit report</button>
        {done && <p className="notice" role="status">{done}</p>}
        <ErrorNote error={error} />
      </form>

      <h2 className="sub-title">Your reports</h2>
      {!list ? <Loading /> : list.length === 0 ? <Empty title="You haven't reported anything." /> : (
        <ul className="report-list">
          {list.map((r) => (
            <li key={r.id}>
              <div>
                <b>{r.entity_value}</b> <span className="label">{r.entity_type}</span>
                <p className="note">{LABEL[r.category]}{r.amount ? ` · ${inr(r.amount)}` : ""}{r.incident_date ? ` · ${r.incident_date}` : ""} · reported {when(r.created_at)}</p>
                {r.description && <p>{r.description}</p>}
              </div>
              <div className="field">
                <label htmlFor={"st" + r.id}>Status</label>
                <select id={"st" + r.id} value={r.status} onChange={async (e) => { await api.updateEntityReport(r.id, e.target.value); load(); }}>
                  {["PENDING", "CONFIRMED_BY_USER", "DISPUTED", "REMOVED"].map((s) => <option key={s} value={s}>{STATUS[s]}</option>)}
                  {r.status === "REVIEWED" && <option value="REVIEWED">{STATUS.REVIEWED}</option>}
                </select>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { ErrorNote, PageHead, Synthetic } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { downloadJson } from "../lib/format.js";

export default function Settings() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [msg, setMsg] = useState("");
  const [error, setError] = useState(null);
  const [password, setPassword] = useState("");
  const [aa, setAa] = useState("idle"); // mock Account Aggregator flow
  const [ai, setAi] = useState(null);   // which AI provider the server uses (for informed consent)
  const s = user.settings || {};
  useEffect(() => { api.aiStatus().then(setAi).catch(() => {}); }, []);

  async function save(body, note) {
    setError(null);
    try {
      const r = await api.updateSettings(body);
      setUser({ ...user, display_name: r.display_name, settings: r.settings });
      setMsg(note + (r.purged ? ` ${r.purged} older transaction(s) deleted.` : ""));
    } catch (err) { setError(err); }
  }
  async function notifications(on) {
    if (on && "Notification" in window && Notification.permission === "default") await Notification.requestPermission();
    save({ notifications: on }, on ? "Notifications on." : "Notifications off.");
  }
  async function exportAll() {
    downloadJson(await api.exportData(), "upi-guard-export.json");
    setMsg("Export downloaded.");
  }
  async function wipe() {
    if (!confirm("Delete all your transactions, cases, notes and alerts? This can't be undone.")) return;
    await api.deleteData();
    setMsg("Your history was deleted.");
  }
  async function closeAccount(e) {
    e.preventDefault();
    if (!confirm("Delete your account and all its data permanently?")) return;
    try {
      await api.deleteAccount(password);
      setUser(null);
      navigate("/");
    } catch (err) { setError(err); }
  }
  async function aaApprove() {
    setAa("fetching");
    try {
      const r = await api.loadDemo();
      setAa("done");
      setMsg(`Simulated bank shared ${r.loaded} synthetic transactions.`);
    } catch (err) { setError(err); setAa("idle"); }
  }

  return (
    <>
      <PageHead kicker="Settings" title="Settings & privacy">Signed in as {user.email}.</PageHead>
      {msg && <p className="notice" role="status">{msg}</p>}
      <ErrorNote error={error} />

      <section className="settings-block">
        <h2>Profile</h2>
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); save({ display_name: e.target.dn.value }, "Name saved."); }}>
          <label htmlFor="dn">Display name</label>
          <input id="dn" name="dn" type="text" maxLength={80} defaultValue={user.display_name} />
          <button type="submit" className="ghost small">Save</button>
        </form>
      </section>

      <section className="settings-block" id="ai">
        <h2>AI investigator</h2>
        <p>When on, the questions you ask and the transaction records needed to answer them (amounts, dates, names, UPI IDs,
          risk evidence) are sent to {ai?.configured ? <b>{ai.provider_label}'s API ({ai.model})</b> : "the AI provider configured on this server"}.
          Nothing is sent until you ask a question. Your PIN, OTP and passwords are never stored, so they can't be sent.</p>
        {ai && !ai.configured && <p className="note">The AI investigator isn't set up on this server, so turning this on has no effect yet.</p>}
        <label className="switch"><input type="checkbox" checked={!!s.ai_consent} onChange={(e) => save({ ai_consent: e.target.checked }, e.target.checked ? "AI investigator on." : "AI investigator off.")} />
          <span>Allow the AI investigator to read my transaction evidence</span></label>
      </section>

      <section className="settings-block">
        <h2>Notifications</h2>
        <p>In-app alerts are always on. Browser notifications are shown only while UPI Guard is open, titled "UPI Guard",
          and are never official bank messages.</p>
        <label className="switch"><input type="checkbox" checked={!!s.notifications} onChange={(e) => notifications(e.target.checked)} />
          <span>Browser notifications for new alerts</span></label>
        {"Notification" in window && Notification.permission === "denied" && <p className="warn-note">Notifications are blocked in your browser settings.</p>}
      </section>

      <section className="settings-block">
        <h2>Data retention</h2>
        <div className="field inline">
          <label htmlFor="ret">Automatically delete transactions older than</label>
          <select id="ret" value={s.retention_days || 0} onChange={(e) => save({ retention_days: Number(e.target.value) }, "Retention updated.")}>
            <option value={0}>Keep until I delete them</option><option value={90}>90 days</option><option value={180}>180 days</option><option value={365}>1 year</option>
          </select>
        </div>
      </section>

      <section className="settings-block">
        <h2>Your data</h2>
        <div className="row-actions">
          <button type="button" className="ghost" onClick={exportAll}>Export all my data (JSON)</button>
          <button type="button" className="ghost danger" onClick={wipe}>Delete transaction history</button>
        </div>
      </section>

      <section className="settings-block">
        <h2>Demo mode</h2>
        <p><Synthetic /> Load or remove the synthetic demo dataset from <Link to="/transactions">History</Link>, or run scenarios in the <Link to="/simulator">simulator</Link>.
          Live demo alerts are on the <Link to="/alerts">Alerts</Link> page.</p>
      </section>

      <section className="settings-block">
        <h2>Connected integrations</h2>
        <p>In India, a real connection to bank data would use the RBI-regulated <b>Account Aggregator</b> framework, where you
          approve consent in an AA app and the bank shares statements directly. UPI Guard is not an Account Aggregator
          and has no bank integration. Below is a <b>simulation</b> of that flow using synthetic data.</p>
        <div className="aa-sim">
          <p className="label">Simulation · Mock Bank → Mock consent → UPI Guard</p>
          {aa === "idle" && <button type="button" className="ghost" onClick={() => setAa("consent")}>Connect "Demo Bank" (simulated)</button>}
          {aa === "consent" && (
            <div className="consent-box">
              <p><b>Demo Bank (simulated)</b> wants to share with UPI Guard:</p>
              <ul className="plain"><li>Purpose: fraud monitoring</li><li>Data: transactions, last 90 days</li><li>Frequency: once</li><li>Expires: 30 days</li></ul>
              <p className="note">A real consent screen never asks for your bank password or UPI PIN, and neither does this one.</p>
              <div className="row-actions">
                <button type="button" className="primary small" onClick={aaApprove}>Approve (simulated)</button>
                <button type="button" className="textbtn" onClick={() => setAa("idle")}>Decline</button>
              </div>
            </div>
          )}
          {aa === "fetching" && <p className="note">Fetching synthetic data…</p>}
          {aa === "done" && <p className="note">Done. Synthetic transactions were added to your history and are labelled.</p>}
        </div>
      </section>

      <section className="settings-block danger-zone">
        <h2>Delete account</h2>
        <form className="inline-form" onSubmit={closeAccount}>
          <label htmlFor="delpw">Confirm with your UPI Guard password</label>
          <input id="delpw" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit" className="ghost danger small" disabled={!password}>Delete account</button>
        </form>
      </section>
    </>
  );
}

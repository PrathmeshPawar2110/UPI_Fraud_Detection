import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { Empty, ErrorNote, Level, Loading, PageHead, Synthetic } from "../components/ui.jsx";
import * as api from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { inr, party, when } from "../lib/format.js";

const STREAM_MS = 5000;

export default function Alerts() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [live, setLive] = useState(false);
  const [feed, setFeed] = useState([]);
  const timer = useRef(null);

  const load = useCallback(() => api.listAlerts().then(setData).catch(setError), []);
  useEffect(() => { load(); return () => clearInterval(timer.current); }, [load]);

  const notify = (a) => {
    if (!user?.settings?.notifications || !("Notification" in window) || Notification.permission !== "granted") return;
    // Clearly not a bank notification: titled UPI Guard, demo data labelled.
    new Notification("UPI Guard (demo): " + a.title, { body: a.body, tag: "upig-" + a.id });
  };

  async function tick() {
    try {
      const r = await api.streamNext();
      setFeed((f) => [r.transaction, ...f].slice(0, 12));
      if (r.alerts.length) {
        r.alerts.forEach(notify);
        load();
        window.dispatchEvent(new Event("upig:alerts"));
      }
    } catch (err) {
      setError(err);
      stop();
    }
  }
  function start() {
    setLive(true);
    tick();
    timer.current = setInterval(tick, STREAM_MS);
  }
  function stop() {
    setLive(false);
    clearInterval(timer.current);
  }

  async function markAll() {
    await api.readAllAlerts();
    load();
    window.dispatchEvent(new Event("upig:alerts"));
  }
  async function open(a) {
    if (!a.read) await api.readAlert(a.id).catch(() => {});
    window.dispatchEvent(new Event("upig:alerts"));
  }

  return (
    <>
      <PageHead kicker="Alert" title="Fraud alerts"
        actions={data?.unread > 0 && <button type="button" className="ghost" onClick={markAll}>Mark all as read</button>}>
        Raised when a saved transaction is high risk or matches a pattern like rapid transfers, repeated payments to a new
        recipient, or paying back someone who just paid you. These are UPI Guard alerts, not messages from your bank.
      </PageHead>

      <section className="panel stream-panel">
        <h2 className="panel-title">Live demo mode <Synthetic small /></h2>
        <p className="muted">Generates a synthetic transaction every {STREAM_MS / 1000} seconds, scores it against your history and
          raises alerts in real time. Mostly everyday payments, occasionally a suspicious one.</p>
        <div className="row-actions">
          {live ? <button type="button" className="primary small" onClick={stop}>Stop stream</button>
            : <button type="button" className="primary small" onClick={start}>Start stream</button>}
          {"Notification" in window && Notification.permission !== "granted" && (
            <button type="button" className="textbtn" onClick={() => Notification.requestPermission()}>Allow browser notifications</button>
          )}
          {!user?.settings?.notifications && <Link to="/settings">Turn on notifications in Settings</Link>}
        </div>
        {feed.length > 0 && (
          <ul className="stream-feed" aria-live="polite">
            {feed.map((t) => (
              <li key={t.id}><Link to={`/investigate/${t.id}`}>{when(t.occurred_at)} · −{inr(t.amount)} → {party(t)}</Link>{" "}
                <Level level={t.risk_level}>{Math.round(t.risk_score * 100)}</Level></li>
            ))}
          </ul>
        )}
      </section>

      <ErrorNote error={error} />
      {!data ? <Loading /> : data.items.length === 0 ? (
        <Empty title="No alerts." >Alerts appear when a saved or imported transaction looks risky. Try the live demo above.</Empty>
      ) : (
        <ul className="alert-list">
          {data.items.map((a) => (
            <li key={a.id} className={"alert-item " + a.severity + (a.read ? " read" : "")}>
              <Level level={a.severity}>{a.severity}</Level>
              <div>
                <p className="alert-title">{!a.read && <span className="sr-only">Unread: </span>}{a.title}</p>
                <p>{a.body}</p>
                <p className="note">{when(a.created_at)}</p>
              </div>
              {a.transaction_id && <Link className="button ghost-link small" to={`/investigate/${a.transaction_id}`} onClick={() => open(a)}>Investigate</Link>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

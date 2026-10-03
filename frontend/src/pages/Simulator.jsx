import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ErrorNote, Level, Loading, PageHead, Stamp, Synthetic } from "../components/ui.jsx";
import { getScenarios, runScenario } from "../lib/api.js";

const KIND = { event: "Event", message: "Message", url: "Link", qr: "QR", tx: "Payment", rx: "Money received" };
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export default function Simulator() {
  const [list, setList] = useState(null);
  const [error, setError] = useState(null);
  const [run, setRun] = useState(null);
  const [shown, setShown] = useState(0);
  const [busy, setBusy] = useState("");
  const timer = useRef(null);

  useEffect(() => { getScenarios().then(setList).catch(setError); return () => clearInterval(timer.current); }, []);

  async function start(id) {
    clearInterval(timer.current);
    setBusy(id);
    setError(null);
    try {
      const r = await runScenario(id);
      setRun(r);
      if (reducedMotion()) return setShown(r.events.length);
      setShown(1);
      let n = 1;
      timer.current = setInterval(() => {
        n += 1;
        setShown(n);
        if (n >= r.events.length) clearInterval(timer.current);
      }, 1100);
    } catch (err) {
      setError(err);
    } finally {
      setBusy("");
    }
  }

  const done = run && shown >= run.events.length;
  return (
    <>
      <PageHead kicker="Simulate" title="Fraud simulation lab">
        Play a scripted scam against a synthetic account and watch each step go through the same engines a real payment
        does: the ML model, rules, history patterns and the message, link and QR scanners.
      </PageHead>
      <p className="synthetic-note"><Synthetic /> {list?.label || "Synthetic demo data — not real bank data"}. Names, UPI IDs and links are invented.</p>
      <ErrorNote error={error} />
      {!list ? <Loading /> : (
        <div className="sim-grid">
          <ul className="scenario-list">
            {list.scenarios.map((s) => (
              <li key={s.id} className={run?.scenario === s.id ? "on" : ""}>
                <button type="button" onClick={() => start(s.id)} disabled={!!busy} aria-pressed={run?.scenario === s.id}>
                  <strong>{s.title}</strong><span>{s.summary}</span>
                </button>
              </li>
            ))}
          </ul>
          <div>
            {!run ? <p className="muted pad">Pick a scenario to run it.</p> : (
              <section aria-live="polite">
                <h2 className="sim-title">{run.title}</h2>
                <p className="muted">{run.summary} Baseline: {run.baseline.transactions} normal transactions over {run.baseline.days} days.</p>
                <ol className="sim-timeline">
                  {run.events.slice(0, shown).map((e, i) => (
                    <li key={i} className={"sim-ev " + (e.level || "none")}>
                      <span className="tl-time">{e.at.slice(11)}<small>{KIND[e.kind]}</small></span>
                      <div>
                        <p className="sim-ev-title">{e.title} {e.level && <Level level={e.level}>{e.score != null ? e.score : e.level}</Level>}</p>
                        {e.kind !== "tx" && e.kind !== "rx" && e.detail && <p className="sim-detail">{e.detail}</p>}
                        {(e.kind === "tx" || e.kind === "rx") && <p className="note">{e.detail}</p>}
                        {e.signals?.length > 0 && <ul className="signals compact">{e.signals.slice(0, 4).map((s, j) => <li key={j}>{s}</li>)}</ul>}
                        {e.breakdown?.length > 0 && (
                          <p className="note">Score: {e.breakdown.filter((b) => b.points >= 0.5).map((b) => `+${b.points.toFixed(0)} ${b.label}`).join(" · ")}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
                {done && (
                  <div className={"sim-result " + run.final_level}>
                    <Stamp level={run.final_level} />
                    <h3>Detected</h3>
                    <ul className="checklist">{run.detected.map((d) => <li key={d.code}><span aria-hidden="true">✓</span> {d.label}</li>)}</ul>
                    <p className="note">What to do in a real case: <Link to="/emergency">emergency steps</Link> · <Link to="/learn">learn about this scam</Link></p>
                  </div>
                )}
                {!done && <button type="button" className="textbtn" onClick={() => { clearInterval(timer.current); setShown(run.events.length); }}>Show all steps</button>}
              </section>
            )}
          </div>
        </div>
      )}
    </>
  );
}

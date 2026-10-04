import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import Graph from "../components/Graph.jsx";
import { Empty, ErrorNote, Level, Loading, PageHead, Synthetic } from "../components/ui.jsx";
import { getEntityNetwork, getNetwork } from "../lib/api.js";
import { inr } from "../lib/format.js";

export default function Network() {
  const [params, setParams] = useSearchParams();
  const focus = params.get("focus");
  const [minRisk, setMinRisk] = useState("");
  const [demo, setDemo] = useState(true);
  const [cycles, setCycles] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    (focus ? getEntityNetwork(encodeURIComponent(focus)) : getNetwork({ min_risk: minRisk, include_demo: demo }))
      .then((d) => { setData(d); setSelected(d.nodes.find((n) => n.id === focus) || null); })
      .catch(setError);
  }, [focus, minRisk, demo]);

  const suspicious = data?.nodes.filter((n) => n.suspicious) || [];
  const partyKey = (n) => n.id.startsWith("party:") ? n.id.slice(6) : null;

  return (
    <>
      <PageHead kicker="Connect" title="Fraud relationship network">
        Who you've paid and been paid by, which devices were used, and how risky entities connect. Built only from your
        own transactions; flows between other accounts appear only in the synthetic demo data.
      </PageHead>

      <div className="filters">
        {focus ? (
          <p>Showing two hops around <b>{focus.replace("party:", "")}</b>. <button type="button" className="textbtn" onClick={() => setParams({})}>Show the whole network</button></p>
        ) : (
          <>
            <div className="field">
              <label htmlFor="minrisk">Show</label>
              <select id="minrisk" value={minRisk} onChange={(e) => setMinRisk(e.target.value)}>
                <option value="">Everything</option><option value="medium">Medium risk and flagged</option><option value="high">High risk and flagged</option>
              </select>
            </div>
            <label className="check"><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> Include synthetic demo flows</label>
          </>
        )}
        <label className="check"><input type="checkbox" checked={cycles} onChange={(e) => setCycles(e.target.checked)} /> Highlight circular flows</label>
      </div>

      <ErrorNote error={error} />
      {!data ? <Loading /> : data.nodes.length <= 1 ? (
        <Empty title="Nothing to connect yet." action={<Link className="button primary-link" to="/transactions">Add transactions or load demo data</Link>}>
          The network is built from your saved transactions.
        </Empty>
      ) : (
        <div className="network-grid">
          <Graph data={data} selected={selected?.id} onSelect={setSelected} highlightCycles={cycles} />
          <aside>
            {selected ? (
              <section className="panel" aria-live="polite">
                <h2 className="panel-title">{selected.kind === "user" ? "You" : selected.label}</h2>
                <p className="label">{selected.kind}{selected.synthetic && <> · <Synthetic small /></>}</p>
                {selected.risk && <p><Level level={selected.risk}>Highest transaction risk: {selected.risk}</Level></p>}
                <dl className="lines">
                  {selected.transactions > 0 && <div><dt>Your transactions</dt><span className="leader" /><dd>{selected.transactions}</dd></div>}
                  {selected.total > 0 && <div><dt>Total</dt><span className="leader" /><dd>{inr(selected.total)}</dd></div>}
                  <div><dt>Connections</dt><span className="leader" /><dd>{selected.degree}</dd></div>
                  {selected.reports > 0 && <div><dt>Community reports</dt><span className="leader" /><dd>{selected.reports} (unverified)</dd></div>}
                </dl>
                {selected.flags?.length > 0 && <ul className="signals">{selected.flags.map((f) => <li key={f}>{f}</li>)}</ul>}
                {partyKey(selected) && (
                  <p className="panel-links">
                    <Link to={`/transactions?q=${encodeURIComponent(partyKey(selected))}`}>Transactions</Link>
                    {selected.kind === "upi" && <Link to={`/before-you-pay?tab=upi&vpa=${encodeURIComponent(partyKey(selected))}`}>Check UPI ID</Link>}
                    <button type="button" className="textbtn" onClick={() => setParams({ focus: selected.id })}>Focus here</button>
                  </p>
                )}
              </section>
            ) : <p className="muted pad">Select an entity to see details.</p>}

            <section className="panel">
              <h2 className="panel-title">Flagged entities ({suspicious.length})</h2>
              {suspicious.length ? (
                <ul className="plain flagged">
                  {suspicious.map((n) => (
                    <li key={n.id}><button type="button" className="textbtn" onClick={() => setSelected(n)}>{n.label}</button>{" "}
                      <Level level={n.risk || "unknown"}>{n.risk || "flag"}</Level>{n.synthetic && <Synthetic small />}</li>
                  ))}
                </ul>
              ) : <p className="muted">No flagged entities.</p>}
              <p className="note">{data.cycles?.length || 0} circular flow(s) · {data.clusters?.length || 0} suspicious cluster(s).
                Flags are patterns, not proof of wrongdoing.</p>
            </section>
          </aside>
        </div>
      )}
    </>
  );
}

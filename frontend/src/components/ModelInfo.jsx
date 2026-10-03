const fmt = (n) => n.toLocaleString("en-IN");

function MetricRow({ name, m, model }) {
  return (
    <tr className={model ? "model" : undefined}>
      <td>{name}</td>
      <td className="num">{m.pr_auc.toFixed(3)}</td>
      <td className="num">{(m.recall * 100).toFixed(1)}%</td>
      <td className="num">{(m.precision * 100).toFixed(1)}%</td>
    </tr>
  );
}

export default function ModelInfo({ info, failed }) {
  let body;
  if (failed) body = <p>Model info unavailable.</p>;
  else if (!info) body = <p>Loading…</p>;
  else {
    const m = info.metrics_test;
    body = (
      <div className="colophon-body">
        <div>
          <p>
            LightGBM trained on {fmt(info.split.rows.train)} of PaySim's 63.6 lakh transactions: transfers and
            cash-outs where the sender's balance covers the amount (99.5% of all frauds), steps 1-400. Tested on{" "}
            {fmt(info.split.rows.test)} later transactions ({fmt(info.split.frauds.test)} frauds) it never saw.
          </p>
          <p>Recall is the share of frauds caught. Precision is the share of alerts that really were fraud.</p>
        </div>
        <table>
          <thead>
            <tr>
              <th className="label">On the test set</th>
              <th className="label num">PR-AUC</th>
              <th className="label num">Recall</th>
              <th className="label num">Precision</th>
            </tr>
          </thead>
          <tbody>
            <MetricRow model name="Model, receiver balances known" m={m.with_receiver_balances} />
            <MetricRow model name="Model, receiver balances unknown" m={m.without_receiver_balances} />
            <MetricRow name="Rule: flagged by simulator" m={m.baseline_isFlaggedFraud} />
            <MetricRow name="Rule: amount over 2 lakh" m={m.baseline_amount_over_200k} />
            <MetricRow name="Rule: sends entire balance" m={m.baseline_empties_account} />
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <section className="sec colophon">
      <div className="sec-head">
        <span className="sec-no">§</span>
        <h2>About the model</h2>
      </div>
      {body}
    </section>
  );
}

const fmt = (n) => n.toLocaleString("en-IN");

function MetricRow({ name, m }) {
  return (
    <tr>
      <td>{name}</td>
      <td className="num">{m.pr_auc.toFixed(3)}</td>
      <td className="num">{(m.recall * 100).toFixed(1)}%</td>
      <td className="num">{(m.precision * 100).toFixed(1)}%</td>
    </tr>
  );
}

export default function ModelInfo({ info, failed }) {
  let body;
  if (failed) body = "Model info unavailable.";
  else if (!info) body = "Loading…";
  else {
    const m = info.metrics_test;
    body = (
      <>
        <p style={{ margin: 0 }}>
          LightGBM trained on {fmt(info.split.rows.train)} PaySim transfers and cash-outs, tested on{" "}
          {fmt(info.split.rows.test)} later transactions ({fmt(info.split.frauds.test)} frauds) it never saw.
        </p>
        <table>
          <tbody>
            <tr><th>On the test set</th><th className="num">PR-AUC</th><th className="num">Recall</th><th className="num">Precision</th></tr>
            <MetricRow name="Model, receiver balances known" m={m.with_receiver_balances} />
            <MetricRow name="Model, receiver balances unknown" m={m.without_receiver_balances} />
            <MetricRow name="Rule: flagged by simulator" m={m.baseline_isFlaggedFraud} />
            <MetricRow name="Rule: amount over 2 lakh" m={m.baseline_amount_over_200k} />
            <MetricRow name="Rule: sends entire balance" m={m.baseline_empties_account} />
          </tbody>
        </table>
        <p style={{ margin: "10px 0 0" }}>Recall = share of frauds caught. Precision = share of alerts that really were fraud.</p>
      </>
    );
  }

  return (
    <section className="card info">
      <h2 style={{ color: "var(--text)" }}>About the model</h2>
      <div>{body}</div>
    </section>
  );
}

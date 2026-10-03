import { Link } from "react-router";
import { DIRECTION, inr, party, when } from "../lib/format.js";

const GLYPH = { low: "●", medium: "▲", high: "■", unknown: "◆" };
const LABEL = { low: "Low risk", medium: "Medium risk", high: "High risk", unknown: "Unknown" };

/** Risk level as text + glyph + colour (never colour alone). */
export function Level({ level, children }) {
  const l = level || "unknown";
  return (
    <span className={"level " + l}>
      <span aria-hidden="true">{GLYPH[l]}</span> {children || LABEL[l]}
    </span>
  );
}

export function Stamp({ level, children }) {
  return <span className={"stamp " + (level || "unknown")}>{children || LABEL[level || "unknown"]}</span>;
}

export function Synthetic({ small }) {
  return <span className={"synthetic" + (small ? " small" : "")} title="Synthetic demo data — not real bank data">Synthetic</span>;
}

export function Section({ no, title, aside, children, className = "" }) {
  return (
    <section className={"sec " + className}>
      <div className="sec-head">
        {no && <span className="sec-no">{no}</span>}
        <h2>{title}</h2>
        {aside && <span className="sec-aside">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export function PageHead({ kicker, title, children, actions }) {
  return (
    <header className="page-head">
      <div>
        {kicker && <p className="label">{kicker}</p>}
        <h1>{title}</h1>
        {children && <p className="lede">{children}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export const Loading = ({ text = "Loading…" }) => <p className="muted pad" role="status">{text}</p>;

export const ErrorNote = ({ error }) => (error ? <p className="error-box" role="alert">{String(error.message || error)}</p> : null);

export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}

export function TxRow({ t, compact }) {
  const arrow = t.direction === "received" ? "←" : "→";
  return (
    <li className={"tx-row" + (compact ? " compact" : "")}>
      <Link to={`/investigate/${t.id}`} className="tx-link">
        <span className={"tx-amount " + t.direction}>{t.direction === "received" ? "+" : "−"}{inr(t.amount)}</span>
        <span className="tx-party">
          <span className="sr-only">{DIRECTION[t.direction]} </span>
          <span aria-hidden="true">{arrow}</span> {party(t)}
          {t.counterparty_name && t.counterparty_upi && <small> · {t.counterparty_name}</small>}
        </span>
        <span className="tx-when">{when(t.occurred_at)}</span>
        <span className="tx-risk">
          <Level level={t.risk_level}>{t.risk_score != null ? `${Math.round(t.risk_score * 100)}` : "–"}</Level>
          {t.is_synthetic && <Synthetic small />}
          {t.review_status !== "unreviewed" && <span className="review-chip">{t.review_status.replace("_", " ")}</span>}
        </span>
      </Link>
    </li>
  );
}

/** "Why risk increased": points each source added to the unified score. */
export function Breakdown({ risk }) {
  if (!risk?.breakdown?.length) return <p className="muted">No risk signals contributed to the score.</p>;
  return (
    <ul className="breakdown">
      {risk.breakdown.map((b, i) => (
        <li key={i}>
          <span className="bd-points">+{b.points.toFixed(0)}</span>
          <span className="bd-bar"><span style={{ width: Math.min(100, b.points) + "%" }} /></span>
          <span className="bd-label">{b.label} <small className="muted">({b.source})</small></span>
        </li>
      ))}
      <li className="bd-total"><span className="bd-points">= {risk.points}</span><span /><span className="bd-label">Unified risk score (0–100)</span></li>
    </ul>
  );
}

export function Reasons({ items }) {
  if (!items?.length) return null;
  return (
    <ul className="reasons">
      {items.map((x, i) => (
        <li key={i} className={x.direction || "up"}>
          <span className="dot" aria-hidden="true">{x.direction === "down" ? "▼" : "▲"}</span>
          <span><span className="sr-only">{x.direction === "down" ? "Lowers risk: " : "Raises risk: "}</span>{x.text}</span>
        </li>
      ))}
    </ul>
  );
}

export function Tabs({ tabs, value, onChange, label }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map(([id, text]) => (
        <button key={id} role="tab" type="button" aria-selected={value === id} className={value === id ? "on" : ""}
                onClick={() => onChange(id)}>{text}</button>
      ))}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router";
import { listAlerts } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";

const TASKS = [
  { to: "/check", icon: "₹", title: "A customer paid me", text: "Check a payment screenshot a customer shows you, before you hand over goods." },
  { to: "/before-you-pay", icon: "⌕", title: "Check before you pay", text: "Scan a QR code, or check a UPI ID, link or message someone sent you." },
  { to: "/statement", icon: "≡", title: "Scan my statement", text: "Upload your bank or UPI statement (Excel or CSV) and check every payment in it." },
  { to: "/help", icon: "!", title: "Lost money? Get help", text: "What to do right now, and who to call.", danger: true },
];

const TIPS = [
  ["Check your bank, not their phone", "A screenshot on the customer's phone is not proof. Wait until the money shows in your own bank app or bank SMS."],
  ["You never need a PIN to receive money", "If anyone asks you to enter your UPI PIN or scan a QR to receive money, it is a scam."],
  ["Never send back a \"wrong transfer\"", "If someone says they paid you by mistake, ask them to contact their bank. Don't return money yourself."],
];

export default function Home() {
  const { user } = useAuth();
  const [alerts, setAlerts] = useState(null);
  useEffect(() => { if (user) listAlerts(true).then(setAlerts).catch(() => {}); }, [user]);

  return (
    <div className="home-simple">
      <header className="home-head">
        <h1>{user ? `Hello${user.display_name ? ", " + user.display_name : ""}.` : "Stay safe from UPI fraud."}</h1>
        <p className="lede">What do you want to do?</p>
      </header>

      <ul className="task-grid">
        {TASKS.map((t) => (
          <li key={t.to}>
            <Link to={t.to} className={"task-card" + (t.danger ? " danger" : "")}>
              <span className="task-icon" aria-hidden="true">{t.icon}</span>
              <span className="task-title">{t.title}</span>
              <span className="task-text">{t.text}</span>
              <span className="task-go" aria-hidden="true">→</span>
            </Link>
          </li>
        ))}
      </ul>

      {user && alerts?.unread > 0 && (
        <section className="home-alerts">
          <h2>You have {alerts.unread} new alert{alerts.unread > 1 ? "s" : ""}</h2>
          <ul>
            {alerts.items.slice(0, 3).map((a) => (
              <li key={a.id}><Link to={a.transaction_id ? `/investigate/${a.transaction_id}` : "/alerts"}><b>{a.title}</b> · {a.body}</Link></li>
            ))}
          </ul>
          <Link to="/alerts">See all alerts →</Link>
        </section>
      )}

      <section className="tips">
        <h2>3 rules that stop most scams</h2>
        <ol>
          {TIPS.map(([t, d]) => <li key={t}><b>{t}.</b> {d}</li>)}
        </ol>
        <Link to="/help">More safety tips →</Link>
      </section>

      {!user && (
        <p className="home-account">
          <Link to="/login?mode=signup">Create a free account</Link> to keep a list of your payments and get alerts.
          Checking a payment works without one.
        </p>
      )}
    </div>
  );
}

import { Link } from "react-router";
import { useAuth } from "../lib/auth.jsx";

// Advanced and occasional tools, kept out of the main navigation so everyday use stays simple.
const TOOLS = [
  ["/check/detailed", "Detailed payment check", "Every field: balances, receiver balances, reference details.", false],
  ["/statement", "Scan a statement", "Upload a bank or UPI statement (PDF, Excel or CSV) and check every payment.", true],
  ["/reports", "Report a scammer", "Warn other users about a UPI ID, phone number or link.", true],
  ["/cases", "Cases & reports", "Group suspicious payments and print a report for your bank or the police.", true],
  ["/alerts", "Alerts", "All warnings about your saved payments, and a live demo.", true],
  ["/network", "Connections map", "See how the people and accounts you've paid are linked.", true],
  ["/simulator", "Scam simulator", "Watch how common scams unfold, step by step (practice data).", false],
  ["/learn", "Scam quiz", "Practise spotting scams.", false],
  ["/settings", "Settings", "Name, AI assistant, notifications, export or delete your data.", true],
  ["/model", "About the fraud model", "How the risk model was built and tested.", false],
];

export default function More() {
  const { user } = useAuth();
  return (
    <div className="guided">
      <h1 className="guided-title">More tools</h1>
      <p className="lede">Extra features. You don't need these for everyday checks.</p>
      <ul className="tool-list">
        {TOOLS.map(([to, title, text, needsAccount]) => (
          <li key={to}>
            <Link to={needsAccount && !user ? `/login?next=${encodeURIComponent(to)}` : to}>
              <span className="tool-title">{title}{needsAccount && !user && <small> · sign in</small>}</span>
              <span className="tool-text">{text}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

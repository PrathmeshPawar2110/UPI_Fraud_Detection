import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { listAlerts } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";

// Four main destinations only, in plain words. Everything else lives under "More tools".
const ICONS = {
  home: <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  check: <><rect x="6" y="2" width="12" height="20" rx="2" /><path d="M9 12l2 2 4-4" /></>,
  pay: <><path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z" /><path d="M12 8v5M12 16h.01" /></>,
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01" /></>,
};
const NAV = [
  ["/", "Home", "home", true],
  ["/check", "Check payment", "check"],
  ["/before-you-pay", "Before you pay", "pay"],
  ["/transactions", "My payments", "list"],
  ["/help", "Help", "help"],
];

const Icon = ({ name }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
);

export default function Layout() {
  const { user, logout } = useAuth();
  const [unread, setUnread] = useState(0);
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => setMenu(false), [location.pathname]);
  useEffect(() => {
    if (!user) return setUnread(0);
    const load = () => listAlerts(true).then((a) => setUnread(a.unread)).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    window.addEventListener("upig:alerts", load);
    return () => { clearInterval(id); window.removeEventListener("upig:alerts", load); };
  }, [user, location.pathname]);

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand" aria-label="UPI Guard home">UPI <em>Guard</em></Link>
          <nav className="main-nav" aria-label="Main">
            {NAV.map(([to, label, icon, end]) => (
              <NavLink key={to} to={to} end={end} className={icon === "help" ? "nav-help" : undefined}>{label}</NavLink>
            ))}
          </nav>
          <div className="topbar-right">
            {user && (
              <NavLink to="/alerts" className="alerts-link" aria-label={`Alerts, ${unread} unread`}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
                </svg>
                {unread > 0 && <span className="badge">{unread > 99 ? "99+" : unread}</span>}
              </NavLink>
            )}
            {user === undefined ? null : user ? (
              <div className="account">
                <button type="button" className="account-btn" aria-expanded={menu} onClick={() => setMenu(!menu)}>
                  {user.display_name || user.email.split("@")[0]} <span aria-hidden="true">▾</span>
                </button>
                {menu && (
                  <div className="account-menu" role="menu">
                    <Link role="menuitem" to="/settings">Settings</Link>
                    <Link role="menuitem" to="/more">More tools</Link>
                    <button role="menuitem" type="button" onClick={async () => { await logout(); navigate("/"); }}>Sign out</button>
                  </div>
                )}
              </div>
            ) : (
              <NavLink to="/login" className="signin-link">Sign in</NavLink>
            )}
          </div>
        </div>
      </header>

      <main id="main" className="wrap">
        <Outlet />
      </main>

      <footer className="wrap site-footer">
        <p>
          UPI Guard never asks for your UPI PIN, OTP or bank password. It is not your bank, NPCI or the police; results
          are warnings, not proof. Lost money? Call <b>1930</b> or report at <b>cybercrime.gov.in</b>.
        </p>
        <p className="footer-links">
          <Link to="/help">Help</Link> · <Link to="/more">More tools</Link> · <Link to="/privacy">Privacy</Link>
        </p>
      </footer>

      {/* Phone: app-style bottom tabs with icons and labels */}
      <nav className="bottom-nav" aria-label="Main (mobile)">
        {NAV.map(([to, label, icon, end]) => (
          <NavLink key={to} to={to} end={end} className={icon === "help" ? "nav-help" : undefined}>
            <Icon name={icon} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  );
}

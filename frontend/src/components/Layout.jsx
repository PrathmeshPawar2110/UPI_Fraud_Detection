import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { listAlerts } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";

const NAV = [
  ["/check", "Check"],
  ["/transactions", "History"],
  ["/scan", "Scan"],
  ["/network", "Network"],
  ["/simulator", "Simulator"],
  ["/cases", "Cases"],
  ["/learn", "Learn"],
];

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => setOpen(false), [location.pathname]);
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
          <button className="menu-btn" type="button" aria-expanded={open} aria-controls="nav" onClick={() => setOpen(!open)}>
            {open ? "Close" : "Menu"}
          </button>
          <nav id="nav" className={open ? "open" : ""} aria-label="Main">
            {NAV.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
            <NavLink to="/emergency" className="nav-emergency">Emergency</NavLink>
          </nav>
          <div className="topbar-right">
            {user && (
              <NavLink to="/alerts" className="alerts-link" aria-label={`Alerts, ${unread} unread`}>
                Alerts{unread > 0 && <span className="badge">{unread > 99 ? "99+" : unread}</span>}
              </NavLink>
            )}
            {user === undefined ? null : user ? (
              <>
                <NavLink to="/settings">{user.display_name || user.email.split("@")[0]}</NavLink>
                <button type="button" className="textbtn" onClick={async () => { await logout(); navigate("/"); }}>Sign out</button>
              </>
            ) : (
              <NavLink to="/login">Sign in</NavLink>
            )}
          </div>
        </div>
      </header>
      <main id="main" className="wrap">
        <Outlet />
      </main>
      <footer className="wrap site-footer">
        <p>
          UPI Guard is an educational project. Risk levels are estimates from a model trained on synthetic PaySim data,
          rules and your own history, not proof of fraud. It is not affiliated with NPCI, RBI or any bank and never asks
          for your UPI PIN, OTP or passwords. Lost money? Call <b>1930</b> or report at <b>cybercrime.gov.in</b>.
        </p>
        <p className="footer-links">
          <Link to="/emergency">Emergency help</Link> · <Link to="/learn">Learn about scams</Link> ·{" "}
          <Link to="/privacy">Privacy</Link> · <Link to="/model">Model</Link>
        </p>
      </footer>
    </>
  );
}

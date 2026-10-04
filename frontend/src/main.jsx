import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";
import Layout from "./components/Layout.jsx";
import { AuthProvider, RequireAuth } from "./lib/auth.jsx";
import Alerts from "./pages/Alerts.jsx";
import { CaseDetail, CaseList, CaseReport } from "./pages/Cases.jsx";
import Check from "./pages/Check.jsx";
import CheckPayment from "./pages/CheckPayment.jsx";
import Help from "./pages/Help.jsx";
import Home from "./pages/Home.jsx";
import { Model, NotFound, Privacy } from "./pages/Info.jsx";
import Investigate from "./pages/Investigate.jsx";
import Learn from "./pages/Learn.jsx";
import Login from "./pages/Login.jsx";
import More from "./pages/More.jsx";
import Network from "./pages/Network.jsx";
import Reports from "./pages/Reports.jsx";
import Scan from "./pages/Scan.jsx";
import Settings from "./pages/Settings.jsx";
import Simulator from "./pages/Simulator.jsx";
import Statement from "./pages/Statement.jsx";
import Transactions from "./pages/Transactions.jsx";
import "./styles.css";
import "./platform.css";

const auth = (el) => <RequireAuth>{el}</RequireAuth>;

// Old addresses keep working (and keep their ?query).
function Moved({ to, tab }) {
  const { search } = useLocation();
  return <Navigate to={to + (tab ? `?tab=${tab}` : search)} replace />;
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="check" element={<CheckPayment />} />
            <Route path="check/detailed" element={<Check />} />
            <Route path="before-you-pay" element={<Scan />} />
            <Route path="help" element={<Help />} />
            <Route path="statement" element={<Statement />} />
            <Route path="more" element={<More />} />
            <Route path="login" element={<Login />} />
            <Route path="scan" element={<Moved to="/before-you-pay" />} />
            <Route path="message-scanner" element={<Moved to="/before-you-pay" tab="message" />} />
            <Route path="url-checker" element={<Moved to="/before-you-pay" tab="url" />} />
            <Route path="qr-scanner" element={<Moved to="/before-you-pay" tab="qr" />} />
            <Route path="upi-check" element={<Moved to="/before-you-pay" tab="upi" />} />
            <Route path="emergency" element={<Moved to="/help" />} />
            <Route path="simulator" element={<Simulator />} />
            <Route path="learn" element={<Learn />} />
            <Route path="privacy" element={<Privacy />} />
            <Route path="model" element={<Model />} />
            <Route path="transactions" element={auth(<Transactions />)} />
            <Route path="investigate/:id" element={auth(<Investigate />)} />
            <Route path="network" element={auth(<Network />)} />
            <Route path="alerts" element={auth(<Alerts />)} />
            <Route path="cases" element={auth(<CaseList />)} />
            <Route path="cases/:id" element={auth(<CaseDetail />)} />
            <Route path="cases/:id/report" element={auth(<CaseReport />)} />
            <Route path="reports" element={auth(<Reports />)} />
            <Route path="settings" element={auth(<Settings />)} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>
);

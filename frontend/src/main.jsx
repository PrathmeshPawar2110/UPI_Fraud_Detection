import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import Layout from "./components/Layout.jsx";
import { AuthProvider, RequireAuth } from "./lib/auth.jsx";
import Alerts from "./pages/Alerts.jsx";
import { CaseDetail, CaseList, CaseReport } from "./pages/Cases.jsx";
import Check from "./pages/Check.jsx";
import Emergency from "./pages/Emergency.jsx";
import Home from "./pages/Home.jsx";
import { Model, NotFound, Privacy } from "./pages/Info.jsx";
import Investigate from "./pages/Investigate.jsx";
import Learn from "./pages/Learn.jsx";
import Login from "./pages/Login.jsx";
import Network from "./pages/Network.jsx";
import Reports from "./pages/Reports.jsx";
import Scan from "./pages/Scan.jsx";
import Settings from "./pages/Settings.jsx";
import Simulator from "./pages/Simulator.jsx";
import Transactions from "./pages/Transactions.jsx";
import "./styles.css";
import "./platform.css";

const auth = (el) => <RequireAuth>{el}</RequireAuth>;

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="check" element={<Check />} />
            <Route path="login" element={<Login />} />
            <Route path="scan" element={<Scan />} />
            <Route path="message-scanner" element={<Navigate to="/scan?tab=message" replace />} />
            <Route path="url-checker" element={<Navigate to="/scan?tab=url" replace />} />
            <Route path="qr-scanner" element={<Navigate to="/scan?tab=qr" replace />} />
            <Route path="upi-check" element={<Navigate to="/scan?tab=upi" replace />} />
            <Route path="simulator" element={<Simulator />} />
            <Route path="learn" element={<Learn />} />
            <Route path="emergency" element={<Emergency />} />
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

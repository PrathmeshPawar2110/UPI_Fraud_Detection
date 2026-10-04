export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const init = { credentials: "same-origin", ...options };
  if (options.body !== undefined && typeof options.body !== "string") {
    init.body = JSON.stringify(options.body);
    init.headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Can't reach the server. Check your connection.", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Something went wrong.", res.status);
  return data;
}

const get = (path, params) => {
  const q = params ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)) : "";
  return request(path + q);
};
const post = (path, body = {}) => request(path, { method: "POST", body });
const patch = (path, body) => request(path, { method: "PATCH", body });
const del = (path, body) => request(path, { method: "DELETE", ...(body ? { body } : {}) });

// Original single-check endpoints (no account needed)
export const getModelInfo = () => get("/api/model-info");
export const predict = (body) => post("/api/predict", body);
export const checkReceived = (body) => post("/api/check-received", body);

// Auth
export const me = () => get("/api/auth/me");
export const signup = (body) => post("/api/auth/signup", body);
export const login = (body) => post("/api/auth/login", body);
export const logout = () => post("/api/auth/logout");

// Transactions & investigation
export const createTransaction = (body) => post("/api/transactions", body);
export const importCsv = (csv) => post("/api/transactions/import", { csv });
export const createTransactionsBatch = (items) => post("/api/transactions/batch", { items });
export const listTransactions = (params) => get("/api/transactions", params);
export const getTransaction = (id) => get(`/api/transactions/${id}`);
export const reviewTransaction = (id, review_status) => patch(`/api/transactions/${id}`, { review_status });
export const deleteTransaction = (id) => del(`/api/transactions/${id}`);
export const updateTransaction = (id, body) => patch(`/api/transactions/${id}`, body);
export const getInvestigation = (id) => get(`/api/investigations/${id}`);
export const addTxNote = (id, text) => post(`/api/investigations/${id}/notes`, { text });

// Scam intelligence
export const analyzeMessage = (text) => post("/api/message/analyze", { text });
export const analyzeUrl = (url) => post("/api/url/analyze", { url });
export const analyzeQr = (payload) => post("/api/qr/analyze", { payload });
export const checkUpi = (vpa) => get(`/api/upi/${encodeURIComponent(vpa)}`);
export const createEntityReport = (body) => post("/api/entity-reports", body);
export const listEntityReports = () => get("/api/entity-reports");
export const updateEntityReport = (id, status) => patch(`/api/entity-reports/${id}`, { status });

// Cases
export const listCases = () => get("/api/cases");
export const createCase = (body) => post("/api/cases", body);
export const getCase = (id) => get(`/api/cases/${id}`);
export const updateCase = (id, body) => patch(`/api/cases/${id}`, body);
export const deleteCase = (id) => del(`/api/cases/${id}`);
export const linkCaseTx = (id, transaction_id) => post(`/api/cases/${id}/transactions`, { transaction_id });
export const addCaseEvidence = (id, body) => post(`/api/cases/${id}/evidence`, body);
export const addCaseNote = (id, text) => post(`/api/cases/${id}/notes`, { text });
export const getCaseReport = (id) => get(`/api/cases/${id}/report`);

// Alerts & guidance
export const listAlerts = (unread_only) => get("/api/alerts", unread_only ? { unread_only: true } : undefined);
export const readAlert = (id) => post(`/api/alerts/${id}/read`);
export const readAllAlerts = () => post("/api/alerts/read-all");
export const getGuidance = () => get("/api/guidance");

// Network, simulator, demo
export const getNetwork = (params) => get("/api/network", params);
export const getEntityNetwork = (id) => get(`/api/network/entity/${id}`);
export const getScenarios = () => get("/api/simulator/scenarios");
export const runScenario = (scenario) => post("/api/simulator/run", { scenario });
export const loadDemo = () => post("/api/demo/load");
export const removeDemo = () => del("/api/demo");
export const streamNext = () => post("/api/simulator/stream/next");

// AI investigator
export const aiStatus = () => get("/api/ai/status");
export const aiAsk = (body) => post("/api/ai/ask", body);

// Account
export const updateSettings = (body) => patch("/api/account/settings", body);
export const exportData = () => get("/api/account/export");
export const deleteData = () => del("/api/account/data");
export const deleteAccount = (password) => del("/api/account", { password });
export const getMonitoring = () => get("/api/model/monitoring");

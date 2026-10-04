# UPI Guard

**A UPI fraud detection, investigation and prevention platform.** It started as *UPI Fraud Check*, a single-payment checker, which is still at its core and unchanged.

| | What it does |
|---|---|
| **Check** | Upload a GPay / PhonePe / Paytm / BHIM screenshot (read in the browser) or type the details. Get a risk level with reasons from an ML model (sent money) or rules (received money) |
| **Detect** | Save payments or import a CSV. A pattern engine compares each one with your history: rapid transfers, new recipient, unusual amount or time, balance drain, repeated payments to a new payee, paying back a recent sender, new device |
| **Explain** | A unified 0–100 risk score shows the points each source added: model (TreeSHAP reasons), rules, patterns, community reports |
| **Investigate** | Timeline, related payments, counterparty profile, notes, review status, and an opt-in AI investigator (Anthropic Claude, OpenAI, Azure OpenAI or Google Gemini) that explains the stored evidence with verified citations |
| **Connect** | Relationship graph with flagged entities, circular money flows and suspicious clusters |
| **Scan** | Suspicious SMS / WhatsApp messages (English, Hinglish), payment links (never opened), QR codes (camera or image) and UPI IDs |
| **Report & act** | Cases with evidence and a printable incident report, community reports (aggregate counts only), alerts, emergency steps (1930, cybercrime.gov.in, Chakshu) |
| **Learn & simulate** | Nine scripted scams run through the same engines on synthetic data; scam explainers with quizzes; a live demo alert stream |

UPI Guard never asks for a UPI PIN, OTP or bank password, labels all synthetic data, and calls things "high-risk patterns", not proof of fraud. Every feature in the expansion spec was checked for feasibility first; what was built, adapted or deferred (and why) is in [TRD §1](docs/TRD.md#1-purpose-and-scope).

The model is LightGBM trained on **PaySim**, as recommended in [data-and-scope.md](data-and-scope.md). It trains on 2,51,957 of PaySim's 63.6 lakh transactions: transfers and cash-outs where the sender's balance covers the amount, steps 1-400. The other rows hold almost no fraud: `CASH_IN`, `PAYMENT` and `DEBIT` have none, and the transfers and cash-outs where the balance doesn't cover the amount hold 45 of the 8,213 frauds (0.5%). The app can't receive those transactions anyway, because a real UPI payment can't exceed the balance.

**Stack:** React 19 + Vite + React Router (`frontend/`) · FastAPI + SQLAlchemy (Postgres / SQLite) + LightGBM-exported model (`backend/`) · Tesseract.js and jsQR in the browser · optional LLM (Anthropic / OpenAI / Azure OpenAI / Gemini) · Vercel + GitHub Actions

Full technical details (architecture, data model, engines, API, security, limitations) are in the **[Technical Reference Document](docs/TRD.md)**.

## Setup

### Prerequisites

- **Python 3.10+**
- **Node.js 20.19+ or 22.12+** (needed by Vite 7) with npm
- Internet access the first time a screenshot is read (Tesseract.js downloads its language data)

The trained model is committed in `backend/app/model/`, so you can run the app without the dataset.

### 1. Clone

```bash
git clone https://github.com/PrathmeshPawar2110/UPI_Fraud_Detection.git
cd UPI_Fraud_Detection
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --port 8000
```

The API runs at http://127.0.0.1:8000. Interactive API docs are at http://127.0.0.1:8000/docs.

Locally, data is stored in a SQLite file, `backend/upi_guard.db` (git-ignored), created on first start. No setup is needed.

To set options, copy `backend/.env.example` to `backend/.env` and fill it in. The file is git-ignored and loaded on start; real environment variables override it:

```powershell
cd backend
copy .env.example .env      # macOS/Linux: cp .env.example .env
```

Options:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local SQLite file | Postgres connection string (required in production) |
| `SECRET_KEY` | random per start (you're signed out on restart) | Signs session cookies (required in production) |
| `AI_PROVIDER` | first provider with a key | `anthropic`, `openai`, `azure` or `gemini` |
| `AI_MODEL` | `claude-opus-5-5` for Anthropic; **required** for OpenAI and Gemini | Model name |
| `AI_DAILY_LIMIT` | 20 | AI questions per user per day |
| Provider keys | unset (AI off) | See the AI investigator table below |

### AI investigator: choose a provider

Set **one** provider's key (plus `AI_MODEL` where needed). With none set, the AI investigator is off and everything else works. The same user-scoped tools, citation checks, consent and daily limit apply to every provider.

| Provider | `AI_PROVIDER` | Required variables | Get a key |
|---|---|---|---|
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` (`AI_MODEL` optional, default `claude-opus-5-5`) | <https://console.anthropic.com> |
| OpenAI | `openai` | `OPENAI_API_KEY`, `AI_MODEL` (a current chat model with tool calling) | <https://platform.openai.com/api-keys> |
| Google Gemini | `gemini` | `GEMINI_API_KEY`, `AI_MODEL` (e.g. a current Gemini Flash / Pro model) | <https://aistudio.google.com/apikey> |
| Azure OpenAI | `azure` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` (`https://<resource>.openai.azure.com`), `AZURE_OPENAI_DEPLOYMENT` (your deployment name); optional `AZURE_OPENAI_API_VERSION` (default `2024-10-21`) | Azure portal → your Azure OpenAI resource → Keys and Endpoint |

Example `backend/.env` for Gemini:

```ini
AI_PROVIDER=gemini
GEMINI_API_KEY=your-key
AI_MODEL=gemini-model-name-from-ai-studio
```

If something is missing, the AI panel (and `GET /api/ai/status`) says exactly which variable to set. Anthropic is called through its own SDK. OpenAI, Azure OpenAI and Gemini all use the official `openai` SDK; Gemini goes through [Google's OpenAI-compatible endpoint](https://ai.google.dev/gemini-api/docs/openai).

If `uvicorn` is "not recognized", the virtual environment isn't active or the dependencies weren't installed into it. Run it through the venv's Python instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --port 8000
```

`--reload-dir app` makes the server watch only the code in `app/`. Without it, uvicorn also watches the thousands of files in `.venv` and keeps restarting whenever OneDrive or pip touches them.

### 3. Frontend (React)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server forwards `/api` requests to the backend on port 8000, so start the backend first.

**Windows:** if PowerShell says "running scripts is disabled on this system" for `npm` (or for `.venv\Scripts\Activate.ps1`), allow local scripts for your user once, then open a new terminal:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Alternatively, use `npm.cmd` (e.g. `npm.cmd run dev`), which skips the blocked `npm.ps1` wrapper.

### Run as a single server (optional)

```bash
cd frontend && npm run build      # writes frontend/dist
cd ../backend && uvicorn app.main:app --port 8000
```

FastAPI serves the built React app and the API together at http://127.0.0.1:8000.

### Open it from your phone or another device (same Wi-Fi)

**Development mode.** Start the backend as usual. Only the frontend needs to listen on the network, because Vite forwards `/api` to the backend on the same machine:

```bash
# terminal 1
cd backend
uvicorn app.main:app --reload --reload-dir app --port 8000

# terminal 2
cd frontend
npm run dev:network               # same as: npm run dev -- --host
```

Vite prints a `Network:` address such as `http://192.168.1.20:5173`. Open that on the other device.

**Single-server mode.** Build once, then let FastAPI listen on all network interfaces:

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://<your-computer's-IP>:8000` on the other device. On Windows, `ipconfig` shows the IP under "IPv4 Address".

If the other device can't connect:
- Allow Python / Node.js through Windows Firewall for **private** networks (Windows asks the first time), and make sure the Wi-Fi is set to a private network.
- Both devices must be on the same network. Some guest and campus Wi-Fi networks block devices from reaching each other.
- Anyone on that network can open the app while it runs. Stop the servers (Ctrl+C) when you're done.

### Retrain the model (optional)

Only needed after changing `train_model.py`.

1. Download the PaySim dataset from Kaggle: <https://www.kaggle.com/datasets/ealaxi/paysim1>. It isn't in the repo because the CSV is about 490 MB.
2. Put the CSV at `Dataset/PS_20174392719_1491204439457_log.csv`.
3. From the project root:

```bash
pip install -r requirements-train.txt   # pandas, numpy, lightgbm
python train_model.py                   # ~2 min; writes fraud_model.txt, trees.json and meta.json
```

Commit all three files in `backend/app/model/`. The API serves `trees.json`, and the tests compare it with `fraud_model.txt`.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest   # 164 tests
cd frontend && npm test                                                  # 8 OCR parser tests
```

- **Original checker:** model info, the 10 sample transactions score as labelled, validation errors, every received-money rule.
- **Predictor parity:** the pure-Python model matches LightGBM's probabilities (to 1e-12) and SHAP values (to 1e-9) on 320 rows.
- **Engines:** every history pattern and its near-misses, unified-risk properties (never below the strongest signal, model-only results unchanged, no double counting), scanners for 11 message scam types, 10 URL verdicts, QR tricks and UPI IDs, secret masking.
- **Platform:** sign-up and sessions, login throttling, another user gets 404 on every record, CSV import, cases and incident reports, aggregate-only community reports, all 9 simulator scenarios, graph cycles, settings, export and deletion, security headers, CSP parity with `vercel.json`, no PIN / OTP fields anywhere in the API.
- **AI investigator:** with fake Anthropic and OpenAI-style clients: provider selection and missing-setting messages, the tool loop for all four providers, Gemini schema conversion, consent, user-scoped tools, citation checking, error mapping, daily limit.
- **OCR parser:** receipts for each app with typical OCR noise (made-up names and numbers).

## Deployment (Vercel, with CI/CD on GitHub Actions)

The whole app runs on Vercel: the React build as static files, and the FastAPI backend as one Python serverless function ([api/index.py](api/index.py)) under the same domain, so `/api` works with no CORS setup.

**The live model runs without LightGBM.** LightGBM plus NumPy and SciPy unpack to ~190 MB, close to Vercel's function size limit, and LightGBM needs the system OpenMP library (`libgomp`). Instead, `train_model.py` exports the trees to `trees.json`, and [predictor.py](backend/app/predictor.py) runs them in pure Python: the same prediction and the same TreeSHAP explanations, checked against LightGBM in the tests. The deployed function needs only FastAPI, SQLAlchemy, the Postgres driver and the Anthropic and OpenAI SDKs (root [requirements.txt](requirements.txt)). It scores a request in ~30 ms.

**Data needs Postgres in production.** Vercel's filesystem is read-only (only `/tmp`, wiped on cold start), so production stops at start-up without `DATABASE_URL`. Preview deployments without it use a throwaway SQLite database in `/tmp`.

**Pipeline** ([.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml)):

| Trigger | What runs |
|---|---|
| Push or pull request to `main` | Backend tests, a check that the function works with runtime dependencies only, OCR parser tests, frontend build |
| Push to `main`, tests passed | Production deploy to Vercel, then a smoke test of the live `/api/model-info` and `/api/predict` |
| Pull request, tests passed | Preview deploy; the URL appears on the workflow run |

Vercel's own Git auto-deploy is turned off in [vercel.json](vercel.json), so nothing deploys unless the tests pass.

**One-time setup:**

1. Create a free account at [vercel.com](https://vercel.com) (sign in with GitHub).
2. Link the project once from your machine, in the repository root:
   ```bash
   npx vercel login
   npx vercel link        # "Set up and deploy?" yes; keep the default settings, vercel.json supplies them
   ```
   This writes `.vercel/project.json` (git-ignored) containing `orgId` and `projectId`.
3. Create a token at <https://vercel.com/account/tokens>.
4. In GitHub, go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   | Secret | Value |
   |---|---|
   | `VERCEL_TOKEN` | the token from step 3 |
   | `VERCEL_ORG_ID` | `orgId` from `.vercel/project.json` |
   | `VERCEL_PROJECT_ID` | `projectId` from `.vercel/project.json` |
5. Create a Postgres database, e.g. a free [Neon](https://neon.tech) project or **Storage → Postgres** in the Vercel dashboard, and copy its connection string.
6. In the Vercel project, go to **Settings → Environment Variables** and add for **Production** (and Preview if you want persistent previews):
   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Postgres connection string |
   | `SECRET_KEY` | a long random string, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | AI provider variables | optional: one provider from the [AI investigator table](#ai-investigator-choose-a-provider) (billed per use, capped by `AI_DAILY_LIMIT`) |

   Tables are created automatically on first start.
7. Push to `main`, or re-run the workflow from the **Actions** tab. The production URL appears on the run and in the Vercel dashboard.

Until the secrets are added, the pipeline still runs the tests and skips the deploy job with a notice.

To deploy by hand instead: `npx vercel` (preview) or `npx vercel --prod` (production) from the repository root.

### API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/predict` | Score a transaction. Body: `type` (`TRANSFER` / `CASH_OUT`), `amount`, `hour` (0-23), `sender_balance_before`, and optionally `sender_balance_after`, `receiver_balance_before`, `receiver_balance_after`. |
| `POST` | `/api/check-received` | Rule-based check for money **received**. Body: `amount`, `hour`, and `knows_sender`, `in_bank`, `asked_to_pay`, each `yes` / `no` / `unsure`. Returns the same shape with `probability: null` and `method: "rules"`. |
| `GET` | `/api/model-info` | Test-set metrics, thresholds and example transactions. |

These three need no account and are unchanged. The platform adds about 40 more endpoints (accounts, transactions, investigation, scanners, cases, alerts, network, simulator, AI, settings), listed in [TRD §28](docs/TRD.md#28-api-reference).

```bash
curl -X POST http://127.0.0.1:8000/api/predict -H "Content-Type: application/json" \
  -d '{"type":"TRANSFER","amount":181000,"hour":3,"sender_balance_before":181000}'
```

Invalid input returns HTTP 400 with `{"detail": "<readable message>"}`.

## How the user gives input

A UPI screenshot shows the amount, date/time, transaction ID / UTR, payee name and UPI ID, and status. It does **not** show balances, which are the strongest fraud signals in PaySim. So the app works in three steps:

| Step | What the user does | Maps to PaySim |
|---|---|---|
| 1. Upload screenshot (optional) | Drop, choose or paste (Ctrl+V) a GPay / PhonePe / Paytm / BHIM receipt, sent or received. OCR runs **in the browser** with Tesseract.js, so the image never leaves the device. | `amount`; time → `step % 24` |
| 2. Confirm details | Pick "Sent money", "Cash withdrawal" or "Received money". For sent money, enter the sender's balance before the payment (from the bank SMS). The balance after is auto-calculated if left blank. | `type`, `oldbalanceOrg`, `newbalanceOrig` |
| 2b. Optional | Receiver's balance before and after (usually only a bank knows these) | `oldbalanceDest`, `newbalanceDest` |
| 2c. Kept for reference | Transaction ID, payee, UPI ID, status from the screenshot. Shown in the result but **not scored**, since PaySim has no such fields. | none |
| 2d. Received money | Three questions instead of balances: do you know the sender, does the money show in your bank, has anyone asked for money back or a fee. Scored with rules (see below). | none |
| 3. Result | Risk level (low / medium / high), fraud score, reasons, and what to do (1930 helpline, cybercrime.gov.in) | |

"Or try a normal / suspicious payment" fills the form with real test-set transactions.

### Screenshot reading

Tested on Google Pay, PhonePe, Paytm and BHIM receipts, both sent and received (light and dark themes). The parser ([ocrParse.js](frontend/src/lib/ocrParse.js)) finds:

- **App**: from its name on the receipt.
- **Direction**: "Money Received", "Received from", "Credited to" or a "From …" heading mean received. "Paid to", "To …", "Debited" or "Paid" mean sent.
- **Amount**: the tallest amount-shaped word on the image, since the headline amount is the largest text on every receipt. OCR often drops it from the plain text or reads ₹ as `Z`, `I` or `%`. Paytm's "Rupees … Only" line is used as a cross-check.
- **Other person**: the name after "From" or "Received from" when received, or after "To", "Paid to" or "Banking Name" when sent, plus the nearest UPI ID (masked IDs keep their visible part).
- **Reference**: the 12-digit UTR / UPI ref is preferred over the app's own transaction ID, because that is the number banks and cybercrime.gov.in ask for.
- **Date and time**: formats like `16 Jul 2026`, `13 Sept 2026`, `1st Oct 26` and `11:09 PM`.

Tesseract runs in sparse-text mode (PSM 11), which keeps the big headline amount that the default page layout misses.

### Received money

The model only learned *outgoing* account-takeover fraud: PaySim has no labelled scams on incoming money. Received payments are therefore scored with transparent rules in [received.py](backend/app/received.py), built on the common incoming-money scams:

| Signal | Risk |
|---|---|
| Money is not in the bank app or SMS (fake "payment received" screenshot) | high |
| Asked to send it back, refund it, or pay a fee or deposit ("wrong transfer", task and job scams) | high |
| Unknown sender and ₹50,000 or more (mule-account pattern) | high |
| Unknown or unsure sender, or unsure whether it arrived | medium |
| Known sender, money in the bank, nobody asking for anything | low |

Receiving money can't take money out of your account by itself, so an unexpected credit is at least medium but only high with a stronger sign. It still matters, because stolen money passing through your account can get the account frozen.

## Modelling decisions

These follow data-and-scope.md, with two additions found during analysis.

- **TRANSFER and CASH_OUT only**, because all PaySim fraud is in these two types. Account IDs and `isFlaggedFraud` are dropped (the flag is kept as a baseline).
- **Time-based split:** train on steps 1-400, validate on 401-550, test on 551-743. Thresholds are tuned on validation only.
- **Realistic rows only (addition).** In about 90% of legit PaySim transfers the amount is larger than the sender's balance and the balances don't add up, which is a simulator bookkeeping artefact. Meanwhile 99.5% of frauds add up exactly. A model trained on all rows learns "balances add up = fraud" and flags every real user, because real balances always add up. The app model is trained only on rows a real user could enter (sender balance > 0 and covers the amount): 281,759 rows that keep 99.5% of all frauds. `errorBalanceOrig` is then always about 0, so it is dropped.
- **Receiver balances optional (addition).** These are hidden (set to NaN) for 50% of training rows, so the model scores well with or without them. LightGBM handles missing values natively.
- **Monotone constraints:** sending a larger share of the balance, or leaving less behind, can never lower the score.
- **Explanations** are TreeSHAP values, the same as LightGBM's `pred_contrib=True` (computed by `predictor.py`), grouped into balance / amount / time / type / receiver.

Features: `is_transfer, amount, hour, oldbalanceOrg, newbalanceOrig, amount_to_balance, drains_account, oldbalanceDest, newbalanceDest, errorBalanceDest`.

## Results (test set: 11,423 later transactions, 2,138 frauds)

| | PR-AUC | Recall | Precision |
|---|---|---|---|
| Model, receiver balances known | 1.000 | 99.9% | 100% |
| Model, receiver balances unknown | 1.000 | 99.5% | 100% |
| Rule: simulator's `isFlaggedFraud` | 0.206 | 0.5% | 100% |
| Rule: amount > 2,00,000 | 0.469 | 67.4% | 58.9% |
| Rule: sends entire balance | 0.980 | 97.1% | 100% |

Read these numbers with care:

- **PaySim is close to separable.** Among realistic rows, *no* legit transaction empties the sender's account, while 98% of frauds do. The one-line rule "sends entire balance" already reaches PR-AUC 0.98. The model's gain comes from the remaining ~2% of frauds (amount, time of day, receiver balances).
- **Expect far lower performance on real UPI data.** Real fraud includes partial transfers, social engineering (the victim pays the scammer themselves), collect-request scams and QR swaps, none of which PaySim simulates.
- **Scores are close to 0 or 1.** Because of the near-separation, the medium band is rare, and partial payments score low even at 4 AM.
- **Amounts are in PaySim's simulated currency**, displayed as ₹. They are not calibrated to typical UPI amounts.

## Files

```
data-and-scope.md                    dataset choice and project scope
docs/TRD.md                          technical reference document
train_model.py                       training, evaluation, saves and exports the model
requirements-train.txt               training dependencies
requirements.txt                     deployed API dependencies (Vercel)
vercel.json                          Vercel build, function and routing settings
api/index.py                         Vercel serverless entry point (imports backend/app)
.github/workflows/ci-cd.yml          tests, then deploy to Vercel

backend/
  requirements.txt                   local API dependencies (FastAPI, uvicorn, SQLAlchemy, pg8000, anthropic, openai)
  requirements-dev.txt               + pytest, httpx, lightgbm for the tests
  app/main.py                        FastAPI app: original endpoints, routers, security headers, SPA fallback
  app/config.py, db.py, models.py    settings, database, tables
  app/auth.py                        accounts and signed session cookies
  app/services.py                    per-user scoring, alerts, related transactions
  app/engine/                        patterns, unified risk, scanners, graph, simulator, CSV import, redaction
  app/routes/                        transactions, intel, cases, alerts, network, simulator, AI, account
  app/schemas.py                     Pydantic request/response models and input validation
  app/fraud.py                       features, scoring, SHAP-based explanations
  app/predictor.py                   pure-Python tree inference + TreeSHAP (no lightgbm at runtime)
  app/received.py                    rule-based check for money received
  app/model/                         trees.json (served), fraud_model.txt (LightGBM), meta.json
  tests/                             164 tests: API, engines, scanners, platform, AI, predictor parity

frontend/
  vite.config.js                     dev server, proxies /api to the backend
  src/main.jsx                       routes
  src/pages/                         Home, Check, History, Investigate, Scan, Network, Simulator, Alerts,
                                     Cases, Reports, Learn, Emergency, Settings, Privacy, Model
  src/components/Layout.jsx, ui.jsx  app shell and shared UI (risk levels, rows, breakdown)
  src/components/AiPanel.jsx, Graph.jsx, QrScanner.jsx
  src/components/UploadCard.jsx      screenshot drop / paste + in-browser OCR (Tesseract.js)
  src/components/TransactionForm.jsx transaction details form
  src/components/ResultCard.jsx      verdict, meter, reasons, advice
  src/components/ModelInfo.jsx       test-set metrics table
  src/lib/ocrParse.js                app, sent/received, amount, time, UTR, other party, UPI ID, status from OCR
  src/lib/ocrParse.test.js           parser tests (node --test)
  src/lib/api.js, auth.jsx           fetch helpers, session context
  src/styles.css, platform.css       styles (light and dark)
```

Note: scikit-learn is not used. On this machine Windows Application Control blocks one of SciPy's DLLs, so the metrics are implemented in numpy in `train_model.py`.

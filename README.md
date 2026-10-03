# UPI Fraud Check

A web app that estimates whether a UPI transaction looks like fraud. The user uploads a payment screenshot (or types the details), confirms a few fields, and gets a risk level with plain-English reasons.

The model is LightGBM trained on **PaySim**, as recommended in [data-and-scope.md](data-and-scope.md). It trains on 2,51,957 of PaySim's 63.6 lakh transactions: transfers and cash-outs where the sender's balance covers the amount, steps 1-400. The other rows hold almost no fraud: `CASH_IN`, `PAYMENT` and `DEBIT` have none, and the transfers and cash-outs where the balance doesn't cover the amount hold 45 of the 8,213 frauds (0.5%). The app can't receive those transactions anyway, because a real UPI payment can't exceed the balance.

**Stack:** React 19 + Vite (`frontend/`) · FastAPI + LightGBM (`backend/`) · Tesseract.js for in-browser OCR

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

### Retrain the model (optional)

Only needed after changing `train_model.py`.

1. Download the PaySim dataset from Kaggle: <https://www.kaggle.com/datasets/ealaxi/paysim1>. It isn't in the repo because the CSV is about 490 MB.
2. Put the CSV at `Dataset/PS_20174392719_1491204439457_log.csv`.
3. From the project root:

```bash
pip install -r requirements.txt   # pandas, numpy, lightgbm
python train_model.py             # ~2 min; writes backend/app/model/fraud_model.txt and meta.json
```

### API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/predict` | Score a transaction. Body: `type` (`TRANSFER` / `CASH_OUT`), `amount`, `hour` (0-23), `sender_balance_before`, and optionally `sender_balance_after`, `receiver_balance_before`, `receiver_balance_after`. |
| `POST` | `/api/check-received` | Rule-based check for money **received**. Body: `amount`, `hour`, and `knows_sender`, `in_bank`, `asked_to_pay`, each `yes` / `no` / `unsure`. Returns the same shape with `probability: null` and `method: "rules"`. |
| `GET` | `/api/model-info` | Test-set metrics, thresholds and example transactions. |

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
- **Explanations** come from LightGBM's built-in SHAP values (`pred_contrib=True`), grouped into balance / amount / time / type / receiver.

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
train_model.py                       training, evaluation, saves the model
requirements.txt                     training dependencies

backend/
  requirements.txt                   API dependencies
  app/main.py                        FastAPI app: POST /api/predict, GET /api/model-info, serves frontend/dist
  app/schemas.py                     Pydantic request/response models and input validation
  app/fraud.py                       model loading, features, SHAP-based explanations
  app/received.py                    rule-based check for money received
  app/model/                         fraud_model.txt (LightGBM), meta.json (thresholds, metrics, samples)

frontend/
  vite.config.js                     dev server, proxies /api to the backend
  src/App.jsx                        form state, samples, calls the API
  src/components/UploadCard.jsx      screenshot drop / paste + in-browser OCR (Tesseract.js)
  src/components/TransactionForm.jsx transaction details form
  src/components/ResultCard.jsx      verdict, meter, reasons, advice
  src/components/ModelInfo.jsx       test-set metrics table
  src/lib/ocrParse.js                app, sent/received, amount, time, UTR, other party, UPI ID, status from OCR
  src/lib/api.js                     fetch helpers
  src/styles.css                     styles (light and dark)
```

Note: scikit-learn is not used. On this machine Windows Application Control blocks one of SciPy's DLLs, so the metrics are implemented in numpy in `train_model.py`.

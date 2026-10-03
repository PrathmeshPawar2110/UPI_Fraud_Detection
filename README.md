# UPI Fraud Check

A web app that estimates whether a UPI transaction looks like fraud. The user uploads a payment screenshot (or types the details), confirms a few fields, and gets a risk level with plain-English reasons.

The model is LightGBM trained on **PaySim**, as recommended in [data-and-scope.md](data-and-scope.md).

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
uvicorn app.main:app --reload --port 8000
```

The API runs at http://127.0.0.1:8000. Interactive API docs are at http://127.0.0.1:8000/docs.

### 3. Frontend (React)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server forwards `/api` requests to the backend on port 8000, so start the backend first.

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
| 1. Upload screenshot (optional) | Drop, choose or paste (Ctrl+V) a GPay / PhonePe / Paytm / BHIM receipt. OCR runs **in the browser** with Tesseract.js, so the image never leaves the device. | `amount`; time → `step % 24` |
| 2. Confirm details | Pick "Sent money" or "Cash withdrawal". Enter the sender's balance before the payment (from the bank SMS). The balance after is auto-calculated if left blank. | `type`, `oldbalanceOrg`, `newbalanceOrig` |
| 2b. Optional | Receiver's balance before and after (usually only a bank knows these) | `oldbalanceDest`, `newbalanceDest` |
| 2c. Kept for reference | Transaction ID, payee, UPI ID, status from the screenshot. Shown in the result but **not scored**, since PaySim has no such fields. | none |
| 3. Result | Risk level (low / medium / high), fraud score, reasons, and what to do (1930 helpline, cybercrime.gov.in) | |

"Try a normal example" and "Try a suspicious example" fill the form with real test-set transactions.

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
  app/model/                         fraud_model.txt (LightGBM), meta.json (thresholds, metrics, samples)

frontend/
  vite.config.js                     dev server, proxies /api to the backend
  src/App.jsx                        form state, samples, calls the API
  src/components/UploadCard.jsx      screenshot drop / paste + in-browser OCR (Tesseract.js)
  src/components/TransactionForm.jsx transaction details form
  src/components/ResultCard.jsx      verdict, meter, reasons, advice
  src/components/ModelInfo.jsx       test-set metrics table
  src/lib/ocrParse.js                extracts amount / time / UTR / payee / UPI ID / status from OCR text
  src/lib/api.js                     fetch helpers
  src/styles.css                     styles (light and dark)
```

Note: scikit-learn is not used. On this machine Windows Application Control blocks one of SciPy's DLLs, so the metrics are implemented in numpy in `train_model.py`.

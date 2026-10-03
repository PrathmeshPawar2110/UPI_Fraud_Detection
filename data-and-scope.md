# UPI Fraud Detection: data and scope

## Candidate datasets

| Dataset | Source | Size | Fraud ratio | Licence | Notes |
|---|---|---|---|---|---|
| **PaySim (recommended)** | [Kaggle: ealaxi/paysim1](https://www.kaggle.com/datasets/ealaxi/paysim1) | ~6.36M rows, 11 cols, ~470 MB CSV | ~0.13% (8,213 frauds) | CC BY-SA 4.0 | Synthetic mobile-money simulator calibrated on real logs from an African mobile-money service. Features: step (hour), type (PAYMENT, TRANSFER, CASH_OUT, DEBIT, CASH_IN), amount, origin/destination IDs and balances before/after, isFraud, isFlaggedFraud. Widely cited, so results can be compared with papers. |
| UPI Transactions 2024 | [Kaggle: skullagos5246/upi-transactions-2024-dataset](https://www.kaggle.com/datasets/skullagos5246/upi-transactions-2024-dataset) | 250,000 rows | ~0.19% (480 frauds) | Not verified (check the Kaggle page) | Synthetic but UPI-flavoured: transaction type, merchant category, device, network, bank, state, amount, time. Good for India-specific EDA. Only 480 frauds, and synthetic labels may be weakly tied to features. |
| Credit Card Fraud (ULB) | [Kaggle: mlg-ulb/creditcardfraud](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) | 284,807 rows, 31 cols | 0.172% (492 frauds) | ODbL | Real European card data, but features V1-V28 are anonymised PCA components, so little to explain. Not UPI-like. Useful only as a benchmark. |

Figures for PaySim and ULB are from their well-known Kaggle descriptions (Kaggle pages could not be fetched from this environment). UPI 2024 figures come from a public analysis of it on GitHub (daisymargarate1309/upi-fraud-detection-analysis).

## Recommendation

Use **PaySim** as the main modelling dataset. No public dataset of real UPI transactions with fraud labels exists (NPCI and banks do not release them), and PaySim's mobile-money peer-to-peer transfers are the closest real-calibrated analogue. It has enough frauds (8k+) to train and evaluate tree models reliably.

Optional: use UPI Transactions 2024 as a secondary dataset to give the report Indian UPI context (categories, states, devices).

## Definition of fraud

A transaction is fraud when `isFraud = 1`: a transfer made by an account taken over by a fraudster, who moves the balance to another account (TRANSFER) and then withdraws it (CASH_OUT). In PaySim fraud occurs only in TRANSFER and CASH_OUT, so the model can be restricted to those two types (~2.77M rows).

Cautions for the modelling thread:
- `isFlaggedFraud` is the simulator's own rule (transfers over 200,000). Drop it as a feature; report it as a rule-based baseline.
- Destination balance columns are often zero for fraud, which looks like leakage. Keep them but note it, and engineer error features (e.g. `oldbalanceOrg - amount - newbalanceOrig`).
- Drop account IDs (`nameOrig`, `nameDest`) as raw features.
- Split by time (`step`): train on earlier hours, test on later, rather than a random split.

## Evaluation metrics

Accuracy is meaningless here (predicting "not fraud" always gives ~99.9%).

- **Primary: PR-AUC (average precision)** - focuses on the rare fraud class.
- **Recall and precision on the fraud class**, plus **F1** (or F2 if missing fraud costs more than a false alarm).
- **Confusion matrix** at the chosen threshold.
- **Recall at a fixed false-positive rate or precision** (e.g. recall at 90% precision), which matches how a bank sets alert budgets.
- ROC-AUC as a secondary number for comparison with papers.
- Use stratified / time-based splits and tune the threshold on validation data, not the test set.

"""Train the fraud model on PaySim and save it for the web app.

Follows data-and-scope.md:
- only TRANSFER and CASH_OUT (the only types with fraud in PaySim)
- drop account IDs and isFlaggedFraud (kept only as a rule-based baseline)
- engineered balance features
- time-based split on `step`, threshold tuned on validation, PR-AUC as primary metric

Realistic-rows filter: in ~90% of legit PaySim transfers the amount is larger than the
sender's balance and the balances do not add up (a simulator bookkeeping artefact), while
99.5% of frauds add up exactly. A model trained on all rows learns "balances add up = fraud",
which flags every real user, because real balances always add up. The app model is trained
only on rows a real user could enter: sender balance > 0 and amount <= balance. This keeps
~99% of the frauds. `errorBalanceOrig` is then ~0 everywhere and is dropped.

Receiver balances are randomly hidden (set to NaN) for half the training rows,
because a real user rarely knows the receiver's balance. LightGBM handles NaN
natively, so the app can score with or without them.

Run:  python train_model.py
"""

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "Dataset" / "PS_20174392719_1491204439457_log.csv"
OUT = ROOT / "backend" / "app" / "model"

TRAIN_END = 400   # steps 1-400 -> train
VAL_END = 550     # steps 401-550 -> validation, 551+ -> test
MASK_RATE = 0.5   # share of training rows with receiver balances hidden
SEED = 42

FEATURES = [
    "is_transfer", "amount", "hour",
    "oldbalanceOrg", "newbalanceOrig", "amount_to_balance", "drains_account",
    "oldbalanceDest", "newbalanceDest", "errorBalanceDest",
]
DEST_FEATURES = ["oldbalanceDest", "newbalanceDest", "errorBalanceDest"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Same logic as backend/app/fraud.py build_row, vectorised."""
    X = pd.DataFrame(index=df.index)
    X["is_transfer"] = (df["type"] == "TRANSFER").astype(np.int8)
    X["amount"] = df["amount"]
    X["hour"] = (df["step"] % 24).astype(np.int8)
    X["oldbalanceOrg"] = df["oldbalanceOrg"]
    X["newbalanceOrig"] = df["newbalanceOrig"]
    X["amount_to_balance"] = df["amount"] / (df["oldbalanceOrg"] + 1.0)
    X["drains_account"] = ((df["newbalanceOrig"] == 0) & (df["oldbalanceOrg"] > 0)).astype(np.int8)
    X["oldbalanceDest"] = df["oldbalanceDest"]
    X["newbalanceDest"] = df["newbalanceDest"]
    X["errorBalanceDest"] = df["oldbalanceDest"] + df["amount"] - df["newbalanceDest"]
    return X[FEATURES]


def export_trees(model: lgb.Booster, path: Path) -> None:
    """Write the trees as compact JSON for backend/app/predictor.py (pure-Python inference + SHAP).

    Internal node: f feature, t threshold, m missing type (0 none, 1 zero, 2 NaN), d default-left,
    c data count, l / r children. Leaf: v value, c data count.
    """
    missing = {"None": 0, "Zero": 1, "NaN": 2}

    def node(n):
        if "leaf_value" in n:
            return {"v": n["leaf_value"], "c": n.get("leaf_count", 0)}
        assert n["decision_type"] == "<=", "only numerical splits are supported"
        return {"f": n["split_feature"], "t": n["threshold"], "m": missing[n["missing_type"]],
                "d": n["default_left"], "c": n["internal_count"],
                "l": node(n["left_child"]), "r": node(n["right_child"])}

    dump = model.dump_model()
    assert dump["objective"].startswith("binary"), dump["objective"]
    trees = [node(t["tree_structure"]) for t in dump["tree_info"]]
    path.write_text(json.dumps({"features": dump["feature_names"], "trees": trees}, separators=(",", ":")))


def hide_dest(X: pd.DataFrame) -> pd.DataFrame:
    X = X.copy()
    X[DEST_FEATURES] = np.nan
    return X


# ---------- metrics (numpy only; scikit-learn is blocked on this machine) ----------

def average_precision(y, s):
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    precision = tp / np.arange(1, len(y) + 1)
    return float((precision * y).sum() / max(y.sum(), 1))


def roc_auc(y, s):
    ranks = pd.Series(s).rank().to_numpy()
    n_pos, n_neg = y.sum(), len(y) - y.sum()
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def at_threshold(y, s, t):
    pred = s >= t
    tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum()); tn = int((~pred & (y == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"threshold": float(t), "precision": p, "recall": r, "f1": f1,
            "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp}}


def pr_curve(y, s):
    """Precision/recall at each distinct score, highest score first."""
    order = np.argsort(-s, kind="mergesort")
    ys, ss = y[order], s[order]
    tp = np.cumsum(ys); fp = np.cumsum(1 - ys)
    last = np.r_[ss[1:] != ss[:-1], True]  # keep last index of each tied score
    return ss[last], tp[last] / (tp[last] + fp[last]), tp[last] / ys.sum()


def recall_at_precision(y, s, target):
    thr, p, r = pr_curve(y, s)
    ok = p >= target
    return (float(r[ok].max()), float(thr[ok][r[ok].argmax()])) if ok.any() else (0.0, 1.0)


def best_f1_threshold(y, s):
    thr, p, r = pr_curve(y, s)
    f1 = np.where(p + r > 0, 2 * p * r / (p + r), 0)
    return float(thr[f1.argmax()])


def threshold_for_recall(y, s, target):
    thr, _, r = pr_curve(y, s)
    return float(thr[np.argmax(r >= target)])


def report(name, y, s, t):
    rec90, _ = recall_at_precision(y, s, 0.90)
    m = {"pr_auc": average_precision(y, s), "roc_auc": roc_auc(y, s),
         "recall_at_90_precision": rec90, **at_threshold(y, s, t)}
    c = m["confusion"]
    print(f"  {name:<34} PR-AUC {m['pr_auc']:.4f}  ROC-AUC {m['roc_auc']:.4f}  "
          f"P {m['precision']:.3f}  R {m['recall']:.3f}  F1 {m['f1']:.3f}  "
          f"R@90%P {rec90:.3f}  TP {c['tp']} FP {c['fp']} FN {c['fn']}")
    return m


def main():
    print("Loading PaySim ...")
    df = pd.read_csv(DATA, usecols=["step", "type", "amount", "oldbalanceOrg", "newbalanceOrig",
                                    "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud"])
    print(f"  {len(df):,} rows, {int(df.isFraud.sum()):,} frauds")
    df = df[df["type"].isin(["TRANSFER", "CASH_OUT"])].reset_index(drop=True)
    n_all, f_all = len(df), int(df.isFraud.sum())
    print(f"  TRANSFER + CASH_OUT: {n_all:,} rows, {f_all:,} frauds")
    realistic = (df.oldbalanceOrg > 0) & (df.amount <= df.oldbalanceOrg + 1)
    df = df[realistic].reset_index(drop=True)
    print(f"  realistic rows (balance > 0 and covers amount): {len(df):,} rows, "
          f"{int(df.isFraud.sum()):,} frauds ({df.isFraud.sum() / f_all:.1%} of all frauds)")

    tr, va, te = df.step <= TRAIN_END, (df.step > TRAIN_END) & (df.step <= VAL_END), df.step > VAL_END
    X = build_features(df)
    y = df["isFraud"].to_numpy()
    for n, m in [("train", tr), ("val", va), ("test", te)]:
        print(f"  {n:<5} {int(m.sum()):>9,} rows  {int(y[m].sum()):>5,} frauds")

    rng = np.random.default_rng(SEED)
    X_tr = X[tr].copy()
    X_tr.loc[rng.random(len(X_tr)) < MASK_RATE, DEST_FEATURES] = np.nan
    # validation: half masked too, so early stopping / threshold suit both input modes
    X_va = X[va].copy()
    X_va.loc[rng.random(len(X_va)) < 0.5, DEST_FEATURES] = np.nan

    # Average precision hits 1.0 after one tree (emptying the account nearly separates the
    # classes), so early-stop on log-loss instead. Regularise and add monotone constraints
    # so a larger share of the balance sent can never lower the risk score.
    monotone = {"newbalanceOrig": -1, "amount_to_balance": 1, "drains_account": 1}
    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31,
              "min_child_samples": 200, "lambda_l2": 10.0, "feature_fraction": 0.9,
              "bagging_fraction": 0.8, "bagging_freq": 1, "metric": "binary_logloss",
              "monotone_constraints": [monotone.get(f, 0) for f in FEATURES],
              "verbose": -1, "seed": SEED}
    print("Training LightGBM ...")
    model = lgb.train(params, lgb.Dataset(X_tr, y[tr]), num_boost_round=500,
                      valid_sets=[lgb.Dataset(X_va, y[va])],
                      callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)])
    print(f"  best iteration: {model.best_iteration}")

    # thresholds from validation only
    s_va = model.predict(X_va, num_iteration=model.best_iteration)
    t_high = best_f1_threshold(y[va], s_va)
    t_med = threshold_for_recall(y[va], s_va, 0.995)
    if t_med >= t_high:
        t_med = t_high / 4
    print(f"  thresholds (val): high-risk >= {t_high:.4f}, medium-risk >= {t_med:.4f}")

    print("Test set (later hours, never seen in training or tuning):")
    X_te, y_te = X[te], y[te]
    s_full = model.predict(X_te, num_iteration=model.best_iteration)
    s_hidden = model.predict(hide_dest(X_te), num_iteration=model.best_iteration)
    metrics = {
        "with_receiver_balances": report("model, receiver balances known", y_te, s_full, t_high),
        "without_receiver_balances": report("model, receiver balances unknown", y_te, s_hidden, t_high),
        "baseline_isFlaggedFraud": report("baseline: isFlaggedFraud rule", y_te,
                                          df.loc[te, "isFlaggedFraud"].to_numpy().astype(float), 0.5),
        "baseline_amount_over_200k": report("baseline: amount > 200,000", y_te,
                                            (df.loc[te, "amount"] > 200_000).to_numpy().astype(float), 0.5),
        "baseline_empties_account": report("baseline: sends entire balance", y_te,
                                           X_te["drains_account"].to_numpy().astype(float), 0.5),
    }

    imp = model.feature_importance("gain")
    importance = sorted(zip(FEATURES, (imp / imp.sum()).tolist()), key=lambda kv: -kv[1])

    # example transactions for the "try a sample" buttons (from the test set)
    cols = ["step", "type", "amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]
    test_df = df[te]
    samples = {
        "legit": test_df[(test_df.isFraud == 0) & (s_full < t_med)].sample(5, random_state=SEED)[cols],
        "fraud": test_df[(test_df.isFraud == 1) & (s_full >= t_high)].sample(5, random_state=SEED)[cols],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    model.save_model(OUT / "fraud_model.txt", num_iteration=model.best_iteration)
    # the deployed API serves the model from this file without lightgbm (see backend/app/predictor.py)
    export_trees(lgb.Booster(model_file=str(OUT / "fraud_model.txt")), OUT / "trees.json")
    meta = {
        "dataset": "PaySim (Kaggle ealaxi/paysim1), TRANSFER + CASH_OUT, sender balance covers amount",
        "rows_before_filter": n_all, "frauds_before_filter": f_all,
        "features": FEATURES,
        "split": {"train_steps": f"1-{TRAIN_END}", "val_steps": f"{TRAIN_END + 1}-{VAL_END}",
                  "test_steps": f"{VAL_END + 1}-743",
                  "rows": {"train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum())},
                  "frauds": {"train": int(y[tr].sum()), "val": int(y[va].sum()), "test": int(y[te].sum())}},
        "thresholds": {"high": t_high, "medium": t_med},
        "best_iteration": model.best_iteration,
        "metrics_test": metrics,
        "feature_importance": importance,
        "samples": {k: v.to_dict(orient="records") for k, v in samples.items()},
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Saved model and metadata to {OUT}")


if __name__ == "__main__":
    main()

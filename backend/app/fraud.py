"""Model loading, feature building and plain-English explanations."""

import json
from pathlib import Path

from .predictor import Model
from .schemas import Transaction

HERE = Path(__file__).parent
MODEL = Model(HERE / "model" / "trees.json")  # exported LightGBM trees, scored in pure Python
META = json.loads((HERE / "model" / "meta.json").read_text(encoding="utf-8"))
FEATURES = META["features"]
assert MODEL.features == FEATURES, "trees.json and meta.json come from different trainings"
T_HIGH, T_MED = META["thresholds"]["high"], META["thresholds"]["medium"]


def build_row(t: Transaction) -> tuple[dict, bool]:
    """Same feature logic as train_model.build_features, for one transaction."""
    amount, before = t.amount, t.sender_balance_before
    after = t.sender_balance_after
    if after is None:
        after = max(before - amount, 0.0)
    dest_known = t.receiver_balance_before is not None and t.receiver_balance_after is not None
    nan = float("nan")
    return {
        "is_transfer": 1 if t.type == "TRANSFER" else 0,
        "amount": amount,
        "hour": t.hour,
        "oldbalanceOrg": before,
        "newbalanceOrig": after,
        "amount_to_balance": amount / (before + 1.0),
        "drains_account": int(after == 0 and before > 0),
        "oldbalanceDest": t.receiver_balance_before if dest_known else nan,
        "newbalanceDest": t.receiver_balance_after if dest_known else nan,
        "errorBalanceDest": (t.receiver_balance_before + amount - t.receiver_balance_after) if dest_known else nan,
    }, dest_known


def inr(x: float) -> str:
    """Indian digit grouping: 12,34,567."""
    neg, x = x < 0, abs(round(x))
    s = str(int(x))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join([head[max(i - 2, 0):i] for i in range(len(head), 0, -2)][::-1])
        s = head + "," + tail
    return ("-" if neg else "") + "₹" + s


def hour_label(h: int) -> str:
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


GROUPS = {
    "balance": ["oldbalanceOrg", "newbalanceOrig", "amount_to_balance", "drains_account"],
    "amount": ["amount"],
    "time": ["hour"],
    "type": ["is_transfer"],
    "receiver": ["oldbalanceDest", "newbalanceDest", "errorBalanceDest"],
}


def explain(row: dict, contrib: dict, dest_known: bool) -> list:
    """Turn SHAP contributions (log-odds) into short plain-English reasons."""
    out = []
    for group, feats in GROUPS.items():
        v = sum(contrib[f] for f in feats)
        if group == "receiver" and not dest_known:
            continue
        up = v > 0
        if group == "balance":
            if row["drains_account"]:
                text = (f"It sends the entire balance ({inr(row['oldbalanceOrg'])}) and leaves the account at ₹0. "
                        "Emptying the account is the most common pattern in account-takeover fraud.")
            else:
                pct = 100 * row["amount_to_balance"]
                text = (f"It uses {pct:.0f}% of the balance and leaves {inr(row['newbalanceOrig'])} in the account. "
                        + ("Frauds usually empty the account." if not up else "That is still a large share of the balance."))
        elif group == "amount":
            text = (f"The amount ({inr(row['amount'])}) is " +
                    ("in the range where frauds are common." if up else "in the range of ordinary payments."))
        elif group == "time":
            h = row["hour"]
            if not up:
                text = f"Made around {hour_label(h)}. Most normal payments happen at this time of day."
            elif h <= 7:
                text = f"Made around {hour_label(h)}. Fraudsters often act in the early hours, while the owner is asleep."
            else:
                text = f"Made around {hour_label(h)}, when fewer normal payments happen, so a larger share are fraud."
        elif group == "type":
            text = ("Direct transfers to another account are the first step of most account takeovers." if row["is_transfer"]
                    else "Cash withdrawals are how fraudsters take the stolen money out." if up
                    else "This payment type does not add much risk here.")
        else:  # receiver
            if row["oldbalanceDest"] == 0 and row["newbalanceDest"] == 0:
                text = "The receiver's balance stayed at ₹0 even after getting the money, as with mule accounts that move funds on immediately."
            elif abs(row["errorBalanceDest"]) > 1:
                text = "The receiver's balance did not go up by the amount sent, so the money may have moved on immediately."
            else:
                text = "The receiver's balance went up by the amount sent, as expected."
        out.append({"group": group, "text": text, "direction": "up" if up else "down", "weight": abs(v)})

    out.sort(key=lambda r: -r["weight"])
    strong = [r for r in out if r["weight"] >= 0.1]
    return (strong or out[:2])[:4]


def meter_position(p: float) -> float:
    """Place the probability on a 3-band meter: low | medium | high, each a third of the bar."""
    if p < T_MED:
        return p / T_MED / 3
    if p < T_HIGH:
        return 1 / 3 + (p - T_MED) / (T_HIGH - T_MED) / 3
    return 2 / 3 + (p - T_HIGH) / (1 - T_HIGH) / 3


def band(p: float) -> str:
    return "high" if p >= T_HIGH else "medium" if p >= T_MED else "low"


def predict_only(t: Transaction) -> dict:
    """Probability and band without SHAP reasons (fast path for bulk scoring)."""
    row, dest_known = build_row(t)
    p = MODEL.predict([float(row[f]) for f in FEATURES])
    return {"probability": p, "risk": band(p), "meter": meter_position(p), "reasons": [],
            "used_receiver_balances": dest_known}


def score(t: Transaction) -> dict:
    row, dest_known = build_row(t)
    x = [float(row[f]) for f in FEATURES]
    p = MODEL.predict(x)
    contrib = dict(zip(FEATURES, MODEL.contributions(x)[:-1]))
    risk = "high" if p >= T_HIGH else "medium" if p >= T_MED else "low"
    return {
        "probability": p,
        "risk": risk,
        "meter": meter_position(p),
        "reasons": [{k: r[k] for k in ("text", "direction", "group")} for r in explain(row, contrib, dest_known)],
        "used_receiver_balances": dest_known,
    }

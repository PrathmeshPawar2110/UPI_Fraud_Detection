"""Unified risk engine: combines the ML model, received-money rules, history patterns and
community reports into one score, keeping every component visible.

Strategy (documented in docs/TRD.md, "Unified risk engine"):

1. Each component produces a severity score s in [0, 1] on a common scale where 0.35 = medium and
   0.70 = high:
   - model:      the LightGBM probability mapped piecewise so its own thresholds land on 0.35 / 0.70
   - rules:      received-money rule level -> low 0.15, medium 0.50, high 0.85
   - patterns:   noisy-OR of the fired patterns' weights, capped at 0.90
   - reputation: unverified community reports on the counterparty -> 0.20 / 0.35 / 0.45 (never high alone)
2. Final score = 1 - prod(1 - s_i)  (noisy-OR, i.e. independent pieces of evidence).
   - The final score is never below the strongest component, so a strong signal can't be averaged away.
   - Adding evidence can only raise the risk; history never suppresses a serious signal.
   - A single component on its own keeps exactly its own level (backward compatible with /api/predict).
3. Level: high >= 0.70, medium >= 0.35, else low.
4. Breakdown: points each source added, applied strongest first, summing to the final score x 100.
"""

from datetime import datetime

from pydantic import ValidationError

from ..fraud import T_HIGH, T_MED, predict_only, score as model_score
from ..received import check_received
from ..schemas import ReceivedPayment, Transaction as ModelInput
from . import patterns as P

VERSION = "risk-v1"
MEDIUM, HIGH = 0.35, 0.70
RULE_SCORE = {"low": 0.15, "medium": 0.50, "high": 0.85}


def level_of(s: float) -> str:
    return "high" if s >= HIGH else "medium" if s >= MEDIUM else "low"


def calibrate_model(p: float) -> float:
    """Map the model probability onto the common scale, keeping its validated thresholds."""
    if p < T_MED:
        return MEDIUM * p / T_MED
    if p < T_HIGH:
        return MEDIUM + (HIGH - MEDIUM) * (p - T_MED) / (T_HIGH - T_MED)
    return HIGH + (1 - HIGH) * (p - T_HIGH) / (1 - T_HIGH)


def noisy_or(scores) -> float:
    acc = 1.0
    for s in scores:
        acc *= 1 - max(0.0, min(1.0, s))
    return 1 - acc


def reputation_score(distinct_reporters: int) -> float:
    return 0.0 if distinct_reporters <= 0 else 0.20 if distinct_reporters == 1 else 0.35 if distinct_reporters == 2 else 0.45


def _model_component(tx, explain: bool) -> dict:
    if tx.direction not in ("sent", "cash_out"):
        return {"available": False, "note": "The model covers money going out only."}
    if tx.balance_before is None:
        return {"available": False, "note": "The model needs the balance before the payment."}
    try:
        inp = ModelInput(
            type="CASH_OUT" if tx.direction == "cash_out" else "TRANSFER",
            amount=tx.amount, hour=tx.occurred_at.hour, sender_balance_before=tx.balance_before,
            sender_balance_after=tx.balance_after, receiver_balance_before=tx.receiver_balance_before,
            receiver_balance_after=tx.receiver_balance_after)
    except ValidationError as e:
        return {"available": False, "note": e.errors()[0]["msg"].removeprefix("Value error, ")}
    if explain:
        r = model_score(inp)
    else:  # bulk imports: probability only (TreeSHAP is ~30 ms per row); explained on first view
        r = predict_only(inp)
    s = calibrate_model(r["probability"])
    return {"available": True, "probability": r["probability"], "score": s, "level": r["risk"],
            "reasons": r["reasons"], "explained": explain, "used_receiver_balances": r["used_receiver_balances"]}


def _rules_component(tx) -> dict:
    ans = tx.received_answers or {}
    if tx.direction != "received":
        return {"available": False}
    if not all(ans.get(k) for k in ("knows_sender", "in_bank", "asked_to_pay")):
        return {"available": False, "note": "Answer the three received-money questions to run these rules."}
    r = check_received(ReceivedPayment(amount=tx.amount, hour=tx.occurred_at.hour, **{
        k: ans[k] for k in ("knows_sender", "in_bank", "asked_to_pay")}))
    return {"available": True, "score": RULE_SCORE[r["risk"]], "level": r["risk"], "reasons": r["reasons"]}


def assess(tx, history, distinct_reporters: int = 0, explain: bool = True, prior=None) -> dict:
    """Score one transaction against the user's history. `tx` and history items follow patterns.Tx.
    Pass `prior` (earlier transactions, oldest first) to skip re-sorting the history in bulk scoring."""
    model = _model_component(tx, explain)
    rules = _rules_component(tx)

    prior = P.prior_of(tx, history) if prior is None else prior
    found = P.detect(tx, prior, presorted=True)
    # Balance depletion is already the model's strongest feature; don't count it twice.
    for p in found:
        if p.code == "BALANCE_DEPLETION" and model["available"]:
            p.informational = True
    scoring = [p for p in found if not p.informational]
    pat_score = min(noisy_or(p.weight for p in scoring), 0.90)
    patterns = {"available": bool(found), "score": pat_score, "level": level_of(pat_score) if scoring else None,
                "items": [p.to_dict() for p in found]}

    rep_score = reputation_score(distinct_reporters)
    reputation = {"available": distinct_reporters > 0, "score": rep_score, "reports": distinct_reporters,
                  "note": "Unverified reports by other UPI Guard users, not an official list."}

    parts = []
    if model["available"]:
        parts.append(("model", "ML model", model["score"]))
    if rules["available"]:
        parts.append(("rules", "Received-money rules", rules["score"]))
    for p in scoring:
        parts.append(("pattern", p.title, p.weight))
    if rep_score:
        parts.append(("reputation", "Community reports", rep_score))

    # Pattern weights are capped as a group; scale them so the breakdown still sums to the final score.
    raw_pat = noisy_or(p.weight for p in scoring)
    scale = (pat_score / raw_pat) if raw_pat > pat_score and raw_pat > 0 else 1.0
    parts = [(src, label, s * scale if src == "pattern" else s) for src, label, s in parts]

    breakdown, acc = [], 0.0
    for src, label, s in sorted(parts, key=lambda x: -x[2]):
        new = 1 - (1 - acc) * (1 - s)
        breakdown.append({"source": src, "label": label, "points": round((new - acc) * 100, 1)})
        acc = new
    final = acc

    reasons = []
    for comp in (model, rules):
        if comp["available"]:
            reasons += comp["reasons"]
    reasons += [{"text": p.detail, "direction": "up", "pattern": p.code} for p in found]

    notes = [c["note"] for c in (model, rules) if c.get("note")]
    if not parts:
        notes.append("No risk signals were found with the information available.")
    return {
        "version": VERSION,
        "score": round(final, 4),
        "points": round(final * 100),
        "level": level_of(final),
        "components": {"model": model, "rules": rules, "patterns": patterns, "reputation": reputation},
        "breakdown": breakdown,
        "reasons": reasons,
        "baseline": P.baseline(prior),
        "notes": notes,
        "assessed_at": datetime.now().isoformat(timespec="seconds"),
    }

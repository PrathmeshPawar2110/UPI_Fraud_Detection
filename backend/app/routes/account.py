"""Account settings, consent, data export / deletion, retention, and model monitoring."""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..auth import COOKIE, audit, current_user, me_out, optional_user, verify_password
from ..db import get_db
from ..fraud import META
from ..models import Alert, Case, EntityReport, Note, Transaction, User, utcnow
from .common import TransactionDetail

router = APIRouter(prefix="/api", tags=["account"])


class SettingsIn(BaseModel):
    ai_consent: Optional[bool] = None
    notifications: Optional[bool] = None
    retention_days: Optional[int] = Field(default=None, ge=0, le=3650)  # 0 = keep forever
    display_name: Optional[str] = Field(default=None, max_length=80)


class Confirm(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def apply_retention(db: Session, user: User) -> int:
    days = (user.settings or {}).get("retention_days") or 0
    if not days:
        return 0
    cutoff = utcnow() - timedelta(days=days)
    return db.execute(delete(Transaction).where(Transaction.user_id == user.id,
                                                Transaction.occurred_at < cutoff)).rowcount


@router.patch("/account/settings")
def update_settings(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    if "display_name" in changes:
        user.display_name = changes.pop("display_name").strip()
    user.settings = {**(user.settings or {}), **changes}
    if "ai_consent" in changes:
        audit(db, user.id, "consent.ai", value=changes["ai_consent"])
    purged = apply_retention(db, user) if "retention_days" in changes else 0
    db.commit()
    return {**me_out(user).model_dump(), "purged": purged}


@router.get("/account/export")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everything stored about the user, as JSON (data portability)."""
    q = lambda model: db.scalars(select(model).where(model.user_id == user.id)).all()
    cases = q(Case)
    audit(db, user.id, "account.export")
    db.commit()
    return {
        "exported_at": utcnow().isoformat(),
        "account": {"email": user.email, "display_name": user.display_name, "created_at": user.created_at.isoformat(),
                    "settings": user.settings},
        "transactions": [TransactionDetail.model_validate(t).model_dump(mode="json") for t in q(Transaction)],
        "cases": [{"id": c.id, "title": c.title, "status": c.status, "priority": c.priority, "resolution": c.resolution,
                   "evidence": c.evidence, "transaction_ids": [t.id for t in c.transactions],
                   "created_at": c.created_at.isoformat()} for c in cases],
        "notes": [{"id": n.id, "transaction_id": n.transaction_id, "case_id": n.case_id, "text": n.text,
                   "created_at": n.created_at.isoformat()} for n in q(Note)],
        "reports": [{"id": r.id, "entity_type": r.entity_type, "entity_value": r.entity_value, "category": r.category,
                     "status": r.status, "description": r.description, "created_at": r.created_at.isoformat()}
                    for r in q(EntityReport)],
        "alerts": [{"title": a.title, "body": a.body, "severity": a.severity, "created_at": a.created_at.isoformat()}
                   for a in q(Alert)],
    }


@router.delete("/account/data")
def delete_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete transactions, cases, notes and alerts (keeps the account and community reports)."""
    for model in (Alert, Note, Case, Transaction):
        db.execute(delete(model).where(model.user_id == user.id))
    audit(db, user.id, "account.delete_data")
    db.commit()
    return {"ok": True}


@router.delete("/account")
def delete_account(body: Confirm, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect.")
    uid = user.id
    for model in (Alert, Note, Case, Transaction, EntityReport):
        db.execute(delete(model).where(model.user_id == uid))
    db.delete(user)
    audit(db, uid, "account.delete")  # audit rows keep only the numeric id
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/model/monitoring")
def monitoring(user: Optional[User] = Depends(optional_user), db: Session = Depends(get_db)):
    """Developer page: model version, test metrics, thresholds, and the live prediction distribution
    over the signed-in user's own scored transactions."""
    m = META["metrics_test"]
    out = {
        "model": {"type": "LightGBM (served as exported trees, pure Python)", "best_iteration": META.get("best_iteration"),
                  "features": META["features"], "dataset": META["dataset"], "split": META["split"]},
        "thresholds": META["thresholds"],
        "test_metrics": {k: {f: v.get(f) for f in ("pr_auc", "roc_auc", "precision", "recall", "f1", "confusion")}
                         for k, v in m.items()},
        "feature_importance": META["feature_importance"],
        "drift": "Not computed: the training feature distribution isn't stored with the model.",
        "live": None,
    }
    if user:
        txs = db.scalars(select(Transaction).where(Transaction.user_id == user.id)).all()
        probs = [((t.risk or {}).get("components", {}).get("model") or {}).get("probability") for t in txs]
        probs = [p for p in probs if p is not None]
        bins = [0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0001]
        out["live"] = {
            "scored": len(txs), "model_scored": len(probs),
            "by_level": {l: sum(t.risk_level == l for t in txs) for l in ("low", "medium", "high")},
            "probability_histogram": [{"from": bins[i], "to": min(bins[i + 1], 1.0),
                                       "count": sum(bins[i] <= p < bins[i + 1] for p in probs)} for i in range(len(bins) - 1)],
            "reviewed": {s: sum(t.review_status == s for t in txs) for s in ("legitimate", "suspicious", "confirmed_fraud")},
            "false_positive_candidates": sum(t.risk_level == "high" and t.review_status == "legitimate" for t in txs),
            "missed_candidates": sum(t.risk_level == "low" and t.review_status == "confirmed_fraud" for t in txs),
        }
    return out

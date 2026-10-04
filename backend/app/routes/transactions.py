"""Transaction history, import, investigation and notes."""

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import config, services as S
from ..auth import audit, current_user
from ..db import get_db
from ..engine import csv_import
from ..engine import upi as U
from ..engine.redact import redact
from ..models import Case, Note, Transaction, User
from .common import ReviewStatus, TransactionDetail, TransactionIn, TransactionOut, own_transaction

router = APIRouter(prefix="/api", tags=["transactions"])


class Page(BaseModel):
    items: list[TransactionOut]
    total: int


class ImportBody(BaseModel):
    csv: str = Field(max_length=900_000)


class ImportResult(BaseModel):
    imported: int
    errors: list[dict]
    high_risk: int


class Review(BaseModel):
    """Update a saved payment: mark it, and/or add the balances a receipt doesn't show (then it's re-scored)."""
    review_status: Optional[ReviewStatus] = None
    balance_before: Optional[float] = Field(default=None, ge=0, le=1e10, allow_inf_nan=False)
    balance_after: Optional[float] = Field(default=None, ge=0, le=1e10, allow_inf_nan=False)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class NoteOut(BaseModel):
    id: int
    text: str
    created_at: datetime


def _build(user: User, body: TransactionIn, synthetic: bool = False) -> Transaction:
    data = body.model_dump()
    answers = data.pop("received_answers")
    return Transaction(user_id=user.id, **data, received_answers=answers, is_synthetic=synthetic)


def _save(db: Session, user: User, body: TransactionIn, synthetic: bool = False) -> Transaction:
    tx = _build(user, body, synthetic)
    db.add(tx)
    db.flush()
    return tx


@router.post("/transactions", response_model=TransactionDetail)
def create(body: TransactionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tx = _save(db, user, body)
    S.score(db, tx, S.history(db, user))
    S.make_alerts(db, user, tx)
    db.commit()
    return tx


@router.post("/transactions/import", response_model=ImportResult)
def import_csv(body: ImportBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        rows, errors = csv_import.parse(body.csv, config.MAX_IMPORT_ROWS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rows:
        raise HTTPException(status_code=400, detail=errors[0]["error"] if errors else "No rows to import.")
    new = [_build(user, r) for r in rows]
    S.rescore_all(db, user, new=new)  # scored before insert: one batched INSERT, no per-row UPDATEs
    for tx in new:
        if tx.risk_level == "high":
            S.make_alerts(db, user, tx)
    audit(db, user.id, "transactions.import", rows=len(new), errors=len(errors))
    db.commit()
    return ImportResult(imported=len(new), errors=errors[:50], high_risk=sum(t.risk_level == "high" for t in new))


MAX_BATCH = 50


class BatchBody(BaseModel):
    items: list[TransactionIn] = Field(min_length=1, max_length=MAX_BATCH)


class BatchResult(BaseModel):
    saved: list[TransactionOut]
    skipped: list[dict]   # {index, reason}
    high_risk: int


@router.post("/transactions/batch", response_model=BatchResult)
def create_batch(body: BatchBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Save several transactions at once (e.g. a batch of scanned screenshots). Payments whose reference
    (UTR) is already in the user's history, or repeated within the batch, are skipped, so scanning the
    same screenshots again doesn't create duplicates."""
    refs = {r.external_id for r in body.items if r.external_id}
    known = set(db.scalars(select(Transaction.external_id).where(
        Transaction.user_id == user.id, Transaction.external_id.in_(refs)))) if refs else set()
    new, skipped, seen = [], [], set()
    for i, item in enumerate(body.items):
        if item.external_id and (item.external_id in known or item.external_id in seen):
            skipped.append({"index": i, "reason": f"Reference {item.external_id} is already in your history."})
            continue
        if item.external_id:
            seen.add(item.external_id)
        new.append(_build(user, item))
    if new:
        S.rescore_all(db, user, new=new)  # scored before insert: one batched INSERT
        for tx in new:
            S.make_alerts(db, user, tx)
    audit(db, user.id, "transactions.batch", saved=len(new), skipped=len(skipped))
    db.commit()
    return BatchResult(saved=new, skipped=skipped, high_risk=sum(t.risk_level == "high" for t in new))


@router.get("/transactions", response_model=Page)
def list_transactions(
    q: Optional[str] = Query(default=None, max_length=120),
    risk: Optional[Literal["low", "medium", "high"]] = None,
    direction: Optional[Literal["sent", "received", "cash_out"]] = None,
    app: Optional[str] = Query(default=None, max_length=40),
    review: Optional[ReviewStatus] = None,
    min_amount: Optional[float] = Query(default=None, ge=0),
    max_amount: Optional[float] = Query(default=None, ge=0),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    synthetic: Optional[bool] = None,
    sort: Literal["newest", "oldest", "risk", "amount"] = "newest",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    from .account import apply_retention
    if apply_retention(db, user):
        db.commit()
    cond = [Transaction.user_id == user.id]
    if q:
        like = f"%{q.strip().lower()}%"
        cond.append(or_(func.lower(Transaction.counterparty_name).like(like),
                        func.lower(Transaction.counterparty_upi).like(like),
                        func.lower(Transaction.external_id).like(like),
                        func.lower(Transaction.note).like(like)))
    if risk:
        cond.append(Transaction.risk_level == risk)
    if direction:
        cond.append(Transaction.direction == direction)
    if app:
        cond.append(func.lower(Transaction.payment_app) == app.lower())
    if review:
        cond.append(Transaction.review_status == review)
    if min_amount is not None:
        cond.append(Transaction.amount >= min_amount)
    if max_amount is not None:
        cond.append(Transaction.amount <= max_amount)
    if date_from:
        cond.append(Transaction.occurred_at >= date_from.replace(tzinfo=None))
    if date_to:
        cond.append(Transaction.occurred_at <= date_to.replace(tzinfo=None))
    if synthetic is not None:
        cond.append(Transaction.is_synthetic.is_(synthetic))
    order = {"newest": [Transaction.occurred_at.desc(), Transaction.id.desc()],
             "oldest": [Transaction.occurred_at, Transaction.id],
             "risk": [Transaction.risk_score.desc(), Transaction.occurred_at.desc()],
             "amount": [Transaction.amount.desc()]}[sort]
    total = db.scalar(select(func.count()).select_from(Transaction).where(*cond))
    items = db.scalars(select(Transaction).where(*cond).order_by(*order).limit(limit).offset(offset)).all()
    return Page(items=items, total=total)


@router.get("/transactions/{tx_id}", response_model=TransactionDetail)
def get_transaction(tx_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return own_transaction(db, user, tx_id)


@router.patch("/transactions/{tx_id}", response_model=TransactionDetail)
def review(tx_id: int, body: Review, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tx = own_transaction(db, user, tx_id)
    if body.review_status is not None:
        tx.review_status = body.review_status
        audit(db, user.id, "transactions.review", transaction_id=tx.id, status=body.review_status)
    fields = body.model_fields_set & {"balance_before", "balance_after"}
    if fields:
        for k in fields:
            setattr(tx, k, getattr(body, k))
        S.score(db, tx, S.history(db, user), explain=True)  # the model can now run
    db.commit()
    return tx


@router.delete("/transactions/{tx_id}")
def delete(tx_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(own_transaction(db, user, tx_id))
    db.commit()
    return {"ok": True}


@router.post("/transactions/rescore")
def rescore(user: User = Depends(current_user), db: Session = Depends(get_db)):
    txs = S.rescore_all(db, user)
    db.commit()
    return {"rescored": len(txs)}


# ---------- investigation ----------

@router.get("/investigations/{tx_id}")
def investigation(tx_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tx = own_transaction(db, user, tx_id)
    txs = S.history(db, user)
    model = ((tx.risk or {}).get("components") or {}).get("model") or {}
    if not tx.risk or (model.get("available") and not model.get("explained")):
        S.score(db, tx, txs, explain=True)  # bulk-imported rows get their SHAP reasons on first view
        db.commit()
    rel = S.related(db, user, tx, txs)
    notes = db.scalars(select(Note).where(Note.user_id == user.id, Note.transaction_id == tx.id)
                       .order_by(Note.created_at)).all()
    cases = db.scalars(select(Case).where(Case.user_id == user.id, Case.transactions.any(Transaction.id == tx.id))).all()
    out = lambda rows: [TransactionOut.model_validate(r).model_dump(mode="json") for r in rows]
    party = [t for t in txs if S.P.party(t) == S.P.party(tx)] if S.P.party(tx) else [tx]
    return {
        "transaction": TransactionDetail.model_validate(tx).model_dump(mode="json"),
        "timeline": out(S.timeline(tx, txs)),
        "related": {"same_counterparty": out(rel["same_counterparty"]), "same_hour": out(rel["same_hour"])},
        "counterparty": {
            **(U.inspect(tx.counterparty_upi) if tx.counterparty_upi else {"vpa": None}),
            "name": tx.counterparty_name,
            "transactions": len(party),
            "total_sent": round(sum(t.amount for t in party if t.direction != "received"), 2),
            "total_received": round(sum(t.amount for t in party if t.direction == "received"), 2),
            "first_seen": min(t.occurred_at for t in party).isoformat(),
            "community_reports": S.reporter_count(db, tx.counterparty_upi),
        },
        "notes": [NoteOut(id=n.id, text=n.text, created_at=n.created_at).model_dump(mode="json") for n in notes],
        "cases": [{"id": c.id, "title": c.title, "status": c.status} for c in cases],
    }


@router.post("/investigations/{tx_id}/notes", response_model=NoteOut)
def add_note(tx_id: int, body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tx = own_transaction(db, user, tx_id)
    note = Note(user_id=user.id, transaction_id=tx.id, text=redact(body.text.strip()))
    db.add(note)
    db.commit()
    return NoteOut(id=note.id, text=note.text, created_at=note.created_at)

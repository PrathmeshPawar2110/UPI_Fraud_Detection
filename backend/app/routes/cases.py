"""Fraud cases: linked transactions, evidence, notes, status workflow and incident reports."""

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services as S
from ..auth import audit, current_user
from ..db import get_db
from ..engine import guidance, upi as U
from ..engine.redact import redact, redact_obj
from ..models import Case, Note, Transaction, User, utcnow
from .common import TransactionOut, own_transaction

router = APIRouter(prefix="/api", tags=["cases"])

Status = Literal["OPEN", "INVESTIGATING", "ESCALATED", "RESOLVED", "FALSE_POSITIVE"]
Priority = Literal["low", "medium", "high"]
EvidenceType = Literal["transaction", "message", "url", "qr", "upi", "screenshot", "note"]


class EvidenceIn(BaseModel):
    type: EvidenceType
    label: str = Field(min_length=1, max_length=140)
    data: dict = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def small(cls, v):
        if len(str(v)) > 8000:
            raise ValueError("Evidence data is too large (keep it under 8 KB; images are not stored).")
        return v


class CaseIn(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    priority: Priority = "medium"
    transaction_ids: list[int] = Field(default_factory=list, max_length=200)
    evidence: list[EvidenceIn] = Field(default_factory=list, max_length=50)


class CaseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=140)
    status: Optional[Status] = None
    priority: Optional[Priority] = None
    resolution: Optional[str] = Field(default=None, max_length=4000)


class LinkTx(BaseModel):
    transaction_id: int


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def own_case(db: Session, user: User, case_id: int) -> Case:
    c = db.get(Case, case_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found.")
    return c


def _evidence(e: EvidenceIn) -> dict:
    return {"type": e.type, "label": redact(e.label), "data": redact_obj(e.data),
            "added_at": datetime.now().isoformat(timespec="seconds")}


def _case_out(db: Session, c: Case, full: bool = False) -> dict:
    out = {"id": c.id, "title": c.title, "status": c.status, "priority": c.priority, "resolution": c.resolution,
           "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
           "transaction_count": len(c.transactions),
           "max_risk": max((t.risk_level for t in c.transactions if t.risk_level),
                           key=lambda l: ["low", "medium", "high"].index(l), default=None)}
    if full:
        notes = db.scalars(select(Note).where(Note.case_id == c.id).order_by(Note.created_at)).all()
        out.update({
            "transactions": [TransactionOut.model_validate(t).model_dump(mode="json") for t in
                             sorted(c.transactions, key=lambda t: t.occurred_at)],
            "evidence": c.evidence or [],
            "notes": [{"id": n.id, "text": n.text, "created_at": n.created_at.isoformat()} for n in notes],
        })
    return out


@router.post("/cases")
def create_case(body: CaseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = Case(user_id=user.id, title=body.title.strip(), priority=body.priority,
             evidence=[_evidence(e) for e in body.evidence])
    c.transactions = [own_transaction(db, user, i) for i in dict.fromkeys(body.transaction_ids)]
    db.add(c)
    audit(db, user.id, "case.create", transactions=len(c.transactions))
    db.commit()
    return _case_out(db, c, full=True)


@router.get("/cases")
def list_cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cases = db.scalars(select(Case).where(Case.user_id == user.id).order_by(Case.updated_at.desc())).all()
    return [_case_out(db, c) for c in cases]


@router.get("/cases/{case_id}")
def get_case(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _case_out(db, own_case(db, user, case_id), full=True)


@router.patch("/cases/{case_id}")
def update_case(case_id: int, body: CaseUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = own_case(db, user, case_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v.strip() if isinstance(v, str) else v)
    c.updated_at = utcnow()
    db.commit()
    return _case_out(db, c, full=True)


@router.delete("/cases/{case_id}")
def delete_case(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(own_case(db, user, case_id))
    db.commit()
    return {"ok": True}


@router.post("/cases/{case_id}/transactions")
def link_transaction(case_id: int, body: LinkTx, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = own_case(db, user, case_id)
    tx = own_transaction(db, user, body.transaction_id)
    if tx not in c.transactions:
        c.transactions.append(tx)
    c.updated_at = utcnow()
    db.commit()
    return _case_out(db, c, full=True)


@router.delete("/cases/{case_id}/transactions/{tx_id}")
def unlink_transaction(case_id: int, tx_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = own_case(db, user, case_id)
    c.transactions = [t for t in c.transactions if t.id != tx_id]
    db.commit()
    return _case_out(db, c, full=True)


@router.post("/cases/{case_id}/evidence")
def add_evidence(case_id: int, body: EvidenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = own_case(db, user, case_id)
    c.evidence = [*(c.evidence or []), _evidence(body)][-100:]
    c.updated_at = utcnow()
    db.commit()
    return _case_out(db, c, full=True)


@router.post("/cases/{case_id}/notes")
def add_case_note(case_id: int, body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = own_case(db, user, case_id)
    db.add(Note(user_id=user.id, case_id=c.id, text=redact(body.text.strip())))
    c.updated_at = utcnow()
    db.commit()
    return _case_out(db, c, full=True)


@router.get("/cases/{case_id}/report")
def incident_report(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Structured incident report built only from stored data (no generated text)."""
    c = own_case(db, user, case_id)
    txs = sorted(c.transactions, key=lambda t: t.occurred_at)
    history = S.history(db, user)
    for t in txs:  # make sure model evidence includes SHAP reasons
        model = ((t.risk or {}).get("components") or {}).get("model") or {}
        if not t.risk or (model.get("available") and not model.get("explained")):
            S.score(db, t, history, explain=True)
    db.commit()
    notes = db.scalars(select(Note).where(Note.case_id == c.id).order_by(Note.created_at)).all()
    levels = [t.risk_level for t in txs if t.risk_level]
    max_level = max(levels, key=lambda l: ["low", "medium", "high"].index(l), default="low")
    sent = [t for t in txs if t.direction != "received"]
    entities = {}
    for t in txs:
        if t.counterparty_upi:
            e = entities.setdefault(t.counterparty_upi, {"type": "upi", "value": t.counterparty_upi,
                                                         "name": t.counterparty_name, "transactions": 0,
                                                         "community_reports": S.reporter_count(db, t.counterparty_upi),
                                                         "app": U.inspect(t.counterparty_upi)["app"]})
            e["transactions"] += 1
    for ev in c.evidence or []:
        for key in ("url", "upi", "phone"):
            val = (ev.get("data") or {}).get(key)
            if val:
                entities.setdefault(f"{key}:{val}", {"type": key, "value": val, "from_evidence": ev["label"]})

    timeline = [{"at": t.occurred_at.isoformat(), "kind": "transaction", "text":
                 f"{t.direction.replace('_', ' ')} ₹{t.amount:,.2f} {'from' if t.direction == 'received' else 'to'} "
                 f"{t.counterparty_upi or t.counterparty_name or 'unknown'} ({(t.risk_level or 'unscored').upper()})",
                 "transaction_id": t.id} for t in txs]
    timeline += [{"at": e["added_at"], "kind": "evidence", "text": f"{e['type']}: {e['label']}"} for e in c.evidence or []]
    timeline += [{"at": n.created_at.isoformat(), "kind": "note", "text": n.text} for n in notes]
    timeline.sort(key=lambda x: x["at"])

    audit(db, user.id, "case.report", case_id=c.id)
    db.commit()
    return {
        "title": "UPI Fraud Incident Report",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "case": {"id": c.id, "title": c.title, "status": c.status, "priority": c.priority,
                 "created_at": c.created_at.isoformat(), "resolution": c.resolution},
        "summary": {
            "transactions": len(txs),
            "total_sent": round(sum(t.amount for t in sent), 2),
            "total_received": round(sum(t.amount for t in txs if t.direction == "received"), 2),
            "from": txs[0].occurred_at.isoformat() if txs else None,
            "to": txs[-1].occurred_at.isoformat() if txs else None,
            "contains_synthetic_data": any(t.is_synthetic for t in txs),
        },
        "risk_assessment": {"highest_level": max_level, "transactions": [
            {"id": t.id, "external_id": t.external_id, "occurred_at": t.occurred_at.isoformat(), "amount": t.amount,
             "direction": t.direction, "counterparty": t.counterparty_upi or t.counterparty_name,
             "score": round((t.risk_score or 0) * 100), "level": t.risk_level,
             "breakdown": (t.risk or {}).get("breakdown", []), "review_status": t.review_status} for t in txs]},
        "model_evidence": [{"transaction_id": t.id, "probability": m.get("probability"), "reasons": m.get("reasons", [])}
                           for t in txs if (m := ((t.risk or {}).get("components") or {}).get("model") or {}).get("available")],
        "rule_evidence": [{"transaction_id": t.id, "level": r.get("level"), "reasons": r.get("reasons", [])}
                          for t in txs if (r := ((t.risk or {}).get("components") or {}).get("rules") or {}).get("available")],
        "pattern_evidence": [{"transaction_id": t.id, "patterns": p.get("items", [])}
                             for t in txs if (p := ((t.risk or {}).get("components") or {}).get("patterns") or {}).get("items")],
        "timeline": timeline,
        "related_entities": list(entities.values()),
        "evidence": c.evidence or [],
        "notes": [{"at": n.created_at.isoformat(), "text": n.text} for n in notes],
        "next_steps": guidance.next_steps(max_level, lost_money=bool(sent),
                                          has_messages=any(e["type"] == "message" for e in c.evidence or [])),
        "resources": guidance.RESOURCES,
        "disclaimer": ("Generated by UPI Guard from the user's own records. Risk levels are estimates from a model "
                       "and rules, not proof of fraud, and do not identify anyone as a criminal."
                       + (" Some transactions are SYNTHETIC DEMO DATA." if any(t.is_synthetic for t in txs) else "")),
    }

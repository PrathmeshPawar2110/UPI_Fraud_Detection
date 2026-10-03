"""Scam intelligence: message, URL, QR and UPI-ID checks, plus community entity reports.

The scanners work without an account (nothing is stored). Signed-in users additionally get their own
history (e.g. "new recipient") folded into the QR and UPI-ID checks.
"""

import re
from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services as S
from ..auth import audit, current_user, optional_user
from ..db import get_db
from ..engine import message as M, qr as Q, upi as U, urls as URL
from ..models import EntityReport, Transaction, User

router = APIRouter(prefix="/api", tags=["scam intelligence"])

CATEGORIES = ["account_takeover", "fake_refund", "kyc", "wrong_transfer", "fake_support", "investment",
              "qr_scam", "phishing", "fake_screenshot", "job_task", "lottery", "digital_arrest", "other"]
REPORT_STATUSES_FOR_REPORTER = {"PENDING", "CONFIRMED_BY_USER", "DISPUTED", "REMOVED"}


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class UrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class QrIn(BaseModel):
    payload: str = Field(min_length=1, max_length=2000)


def _url_reports(db: Session, url: str) -> int:
    r = URL.analyze(url)
    host = (r.get("url") or {}).get("host")
    if not host:
        return 0
    return db.scalar(select(func.count(func.distinct(EntityReport.user_id))).where(
        EntityReport.entity_type == "url", EntityReport.entity_value == host, EntityReport.status != "REMOVED")) or 0


@router.post("/message/analyze")
def analyze_message(body: TextIn):
    return M.analyze(body.text)


@router.post("/url/analyze")
def analyze_url(body: UrlIn, db: Session = Depends(get_db)):
    return URL.analyze(body.url, reports=_url_reports(db, body.url))


@router.post("/qr/analyze")
def analyze_qr(body: QrIn, user: Optional[User] = Depends(optional_user), db: Session = Depends(get_db)):
    parsed = Q.parse_upi(body.payload)
    vpa = U.normalise((parsed or {}).get("params", {}).get("pa", "")) if parsed else ""
    known = None
    if user and vpa:
        known = bool(db.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.user_id == user.id, Transaction.counterparty_upi == vpa)))
    return Q.analyze(body.payload, known_party=known, reports=S.reporter_count(db, vpa) if vpa else 0)


@router.get("/upi/{vpa}")
def check_upi(vpa: str, user: Optional[User] = Depends(optional_user), db: Session = Depends(get_db)):
    if len(vpa) > 300:
        raise HTTPException(status_code=400, detail="UPI ID is too long.")
    info = U.inspect(vpa)
    v = info["vpa"]
    rows = db.execute(select(EntityReport.category, func.count(func.distinct(EntityReport.user_id))).where(
        EntityReport.entity_type == "upi", EntityReport.entity_value == v, EntityReport.status != "REMOVED")
        .group_by(EntityReport.category)).all()
    reports = {"total_reporters": S.reporter_count(db, v), "by_category": {c: n for c, n in rows},
               "note": "Unverified reports by UPI Guard users. Not an official NPCI or bank list, and not proof of wrongdoing."}
    history = None
    if user and info["valid"]:
        txs = db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.counterparty_upi == v)
                         .order_by(Transaction.occurred_at.desc())).all()
        history = {
            "count": len(txs),
            "total_sent": round(sum(t.amount for t in txs if t.direction != "received"), 2),
            "total_received": round(sum(t.amount for t in txs if t.direction == "received"), 2),
            "first_seen": txs[-1].occurred_at.isoformat() if txs else None,
            "last_seen": txs[0].occurred_at.isoformat() if txs else None,
            "high_risk": sum(t.risk_level == "high" for t in txs),
            "recent": [{"id": t.id, "occurred_at": t.occurred_at.isoformat(), "amount": t.amount,
                        "direction": t.direction, "risk_level": t.risk_level} for t in txs[:10]],
        }
    signals = list(info["signals"])
    if reports["total_reporters"]:
        signals.append({"code": "REPORTED", "severity": "medium" if reports["total_reporters"] < 3 else "high",
                        "text": f"Reported by {reports['total_reporters']} UPI Guard user(s) (unverified)."})
    if history and history["high_risk"]:
        signals.append({"code": "HIGH_RISK_HISTORY", "severity": "medium",
                        "text": f"{history['high_risk']} of your transactions with this ID were high risk."})
    sev = [s["severity"] for s in signals]
    level = "high" if "high" in sev else "medium" if "medium" in sev else ("low" if info["valid"] else "unknown")
    return {**info, "signals": signals, "level": level, "reports": reports, "history": history}


# ---------- community entity reports ----------

class ReportIn(BaseModel):
    entity_type: Literal["upi", "phone", "url"]
    entity_value: str = Field(min_length=3, max_length=300)
    category: Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]
    amount: Optional[float] = Field(default=None, gt=0, le=1e9)
    incident_date: Optional[date] = None
    description: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("incident_date")
    @classmethod
    def not_future(cls, v):
        if v and v > date.today():
            raise ValueError("Incident date can't be in the future.")
        return v


class ReportOut(BaseModel):
    id: int
    entity_type: str
    entity_value: str
    category: str
    amount: Optional[float]
    incident_date: Optional[str]
    description: Optional[str]
    status: str
    created_at: datetime


class ReportStatus(BaseModel):
    status: Literal["PENDING", "CONFIRMED_BY_USER", "DISPUTED", "REMOVED"]


def _normalise_entity(kind: str, value: str) -> str:
    v = value.strip()
    if kind == "upi":
        if not U.is_valid(v):
            raise HTTPException(status_code=400, detail="UPI ID must look like name@handle.")
        return U.normalise(v)
    if kind == "phone":
        digits = re.sub(r"\D", "", v)
        digits = digits[2:] if len(digits) == 12 and digits.startswith("91") else digits
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise HTTPException(status_code=400, detail="Enter a 10-digit Indian mobile number.")
        return digits
    host = (URL.analyze(v).get("url") or {}).get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Enter a valid web address.")
    return host


def _out(r: EntityReport) -> ReportOut:
    return ReportOut(id=r.id, entity_type=r.entity_type, entity_value=r.entity_value, category=r.category,
                     amount=r.amount, incident_date=r.incident_date, description=r.description, status=r.status,
                     created_at=r.created_at)


@router.post("/entity-reports", response_model=ReportOut)
def create_report(body: ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = EntityReport(user_id=user.id, entity_type=body.entity_type,
                     entity_value=_normalise_entity(body.entity_type, body.entity_value),
                     category=body.category, amount=body.amount,
                     incident_date=body.incident_date.isoformat() if body.incident_date else None,
                     description=(body.description or "").strip() or None)
    db.add(r)
    audit(db, user.id, "report.create", entity_type=r.entity_type, category=r.category)
    db.commit()
    return _out(r)


@router.get("/entity-reports", response_model=list[ReportOut])
def my_reports(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Only the signed-in user's own reports."""
    return [_out(r) for r in db.scalars(select(EntityReport).where(EntityReport.user_id == user.id)
                                        .order_by(EntityReport.created_at.desc()))]


@router.patch("/entity-reports/{report_id}", response_model=ReportOut)
def update_report(report_id: int, body: ReportStatus, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(EntityReport, report_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="Report not found.")
    r.status = body.status
    db.commit()
    return _out(r)

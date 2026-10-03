"""Fraud simulator, demo dataset and the live demo stream. Everything here is synthetic and labelled."""

import random
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .. import services as S
from ..auth import audit, current_user
from ..db import get_db
from ..engine import simulator as SIM
from ..models import Alert, Transaction, User
from .common import TransactionDetail

router = APIRouter(prefix="/api", tags=["simulator"])


class RunBody(BaseModel):
    scenario: Literal[tuple(SIM.SCENARIOS)]  # type: ignore[valid-type]


@router.get("/simulator/scenarios")
def scenarios():
    return {"label": SIM.SYNTHETIC_LABEL, "scenarios": SIM.list_scenarios()}


@router.post("/simulator/run")
def run(body: RunBody):
    """Stateless: plays the scenario against a synthetic baseline; nothing is stored."""
    return SIM.run(body.scenario)


def _to_row(user: User, t: SIM.SimTx, source: str) -> Transaction:
    return Transaction(user_id=user.id, occurred_at=t.occurred_at, direction=t.direction, amount=t.amount,
                       counterparty_name=t.counterparty_name, counterparty_upi=t.counterparty_upi,
                       balance_before=t.balance_before, balance_after=t.balance_after, device_id=t.device_id,
                       location=t.location, category=t.category, payment_app=t.payment_app,
                       received_answers=t.received_answers, source=source, is_synthetic=True,
                       note=SIM.SYNTHETIC_LABEL)


@router.post("/demo/load")
def load_demo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Add the synthetic demo dataset to the user's history (clearly flagged, removable)."""
    db.execute(delete(Transaction).where(Transaction.user_id == user.id, Transaction.source == "demo"))
    rows = [_to_row(user, t, "demo") for t in SIM.demo_dataset(datetime.now())]
    db.add_all(rows)
    db.flush()
    S.rescore_all(db, user)
    for t in rows:
        if t.risk_level == "high":
            S.make_alerts(db, user, t)
    user.settings = {**(user.settings or {}), "demo_mode": True}
    audit(db, user.id, "demo.load", rows=len(rows))
    db.commit()
    return {"loaded": len(rows), "high_risk": sum(t.risk_level == "high" for t in rows), "label": SIM.SYNTHETIC_LABEL}


@router.delete("/demo")
def remove_demo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.execute(delete(Transaction).where(Transaction.user_id == user.id, Transaction.is_synthetic.is_(True))).rowcount
    db.execute(delete(Alert).where(Alert.user_id == user.id, Alert.transaction_id.is_(None)))
    user.settings = {**(user.settings or {}), "demo_mode": False}
    S.rescore_all(db, user)
    db.commit()
    return {"removed": n}


@router.post("/simulator/stream/next", response_model=dict)
def stream_next(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo mode: create one synthetic 'live' transaction, score it, and return it with any alerts."""
    history = S.history(db, user)
    t = SIM.stream_transaction(history, random.Random(), datetime.now().replace(microsecond=0))
    row = _to_row(user, t, "stream")
    db.add(row)
    db.flush()
    S.score(db, row, history + [row])
    alerts = S.make_alerts(db, user, row)
    db.commit()
    return {"transaction": TransactionDetail.model_validate(row).model_dump(mode="json"),
            "alerts": [{"id": a.id, "title": a.title, "body": a.body, "severity": a.severity, "kind": a.kind}
                       for a in alerts],
            "label": SIM.SYNTHETIC_LABEL}

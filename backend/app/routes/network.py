"""Relationship graph API (the user's own transactions; synthetic demo flows are labelled)."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services as S
from ..auth import current_user
from ..db import get_db
from ..engine import graph as G
from ..models import EntityReport, User
from .common import own_transaction

router = APIRouter(prefix="/api", tags=["network"])


def _graph(db: Session, user: User, include_demo: bool) -> dict:
    txs = S.history(db, user)
    upis = {t.counterparty_upi for t in txs if t.counterparty_upi}
    reports = {}
    if upis:
        rows = db.execute(select(EntityReport.entity_value, func.count(func.distinct(EntityReport.user_id))).where(
            EntityReport.entity_type == "upi", EntityReport.entity_value.in_(upis), EntityReport.status != "REMOVED")
            .group_by(EntityReport.entity_value)).all()
        reports = {v: n for v, n in rows}
    return G.build(txs, reports, include_demo_flows=include_demo)


@router.get("/network")
def network(min_risk: Optional[Literal["medium", "high"]] = None, include_demo: bool = True,
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _graph(db, user, include_demo)
    if min_risk:
        ok = {"medium": ("medium", "high"), "high": ("high",)}[min_risk]
        keep = {n["id"] for n in g["nodes"] if n["kind"] == "user" or n["risk"] in ok or n["suspicious"]}
        g = {**g, "nodes": [n for n in g["nodes"] if n["id"] in keep],
             "edges": [e for e in g["edges"] if e["source"] in keep and e["target"] in keep]}
    return g


@router.get("/network/entity/{entity_id:path}")
def entity(entity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _graph(db, user, True)
    if entity_id not in {n["id"] for n in g["nodes"]}:
        raise HTTPException(status_code=404, detail="Entity not found in your network.")
    return G.ego(g, entity_id, depth=2)


@router.get("/network/transaction/{tx_id}")
def around_transaction(tx_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tx = own_transaction(db, user, tx_id)
    key = (tx.counterparty_upi or tx.counterparty_name or "").strip().lower()
    g = _graph(db, user, True)
    return G.ego(g, f"party:{key}" if key else "you", depth=2)

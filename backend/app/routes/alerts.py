"""In-app fraud alerts (created when transactions are scored)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..engine.guidance import EMERGENCY_STEPS, RESOURCES
from ..models import Alert, User

router = APIRouter(prefix="/api", tags=["alerts"])


def _out(a: Alert) -> dict:
    return {"id": a.id, "transaction_id": a.transaction_id, "kind": a.kind, "severity": a.severity,
            "title": a.title, "body": a.body, "read": a.read, "created_at": a.created_at.isoformat()}


@router.get("/alerts")
def list_alerts(unread_only: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cond = [Alert.user_id == user.id] + ([Alert.read.is_(False)] if unread_only else [])
    rows = db.scalars(select(Alert).where(*cond).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(200)).all()
    unread = sum(not a.read for a in rows)
    return {"items": [_out(a) for a in rows], "unread": unread}


@router.post("/alerts/{alert_id}/read")
def mark_read(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found.")
    a.read = True
    db.commit()
    return _out(a)


@router.post("/alerts/read-all")
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(Alert).where(Alert.user_id == user.id).values(read=True))
    db.commit()
    return {"ok": True}


@router.get("/guidance")
def guidance():
    """Emergency steps and official resources (public)."""
    return {"steps": EMERGENCY_STEPS, "resources": RESOURCES}

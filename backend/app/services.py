"""Shared operations on a user's data: scoring, saving, alerts, related transactions, reputation.

Every function takes the user and filters on user_id; nothing here reads another user's rows except
`reporter_count`, which only returns an aggregate count.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .engine import patterns as P
from .engine.risk import assess
from .models import Alert, EntityReport, Transaction, User

ALERT_PATTERNS = {"RAPID_TRANSFER", "RECIPIENT_CONCENTRATION", "REFUND_LOOP", "TRANSACTION_BURST", "NEW_DEVICE"}


def history(db: Session, user: User) -> list[Transaction]:
    return list(db.scalars(select(Transaction).where(Transaction.user_id == user.id)
                           .order_by(Transaction.occurred_at, Transaction.id)))


def reporter_count(db: Session, upi: str | None) -> int:
    """Distinct users who reported this UPI ID (aggregate only; reporters are never revealed)."""
    if not upi:
        return 0
    return db.scalar(select(func.count(func.distinct(EntityReport.user_id))).where(
        EntityReport.entity_type == "upi", EntityReport.entity_value == upi.strip().lower(),
        EntityReport.status != "REMOVED")) or 0


def score(db: Session, tx: Transaction, txs: list[Transaction] | None = None, explain: bool = True,
          prior: list[Transaction] | None = None) -> None:
    result = assess(tx, txs or [], reporter_count(db, tx.counterparty_upi), explain=explain, prior=prior)
    tx.risk, tx.risk_score, tx.risk_level = result, result["score"], result["level"]


def make_alerts(db: Session, user: User, tx: Transaction) -> list[Alert]:
    """In-app alerts for a newly scored transaction (never claims fraud, only 'high-risk pattern')."""
    out = []
    amount = P._inr(tx.amount)
    who = tx.counterparty_upi or tx.counterparty_name or "unknown recipient"
    arrow = "←" if tx.direction == "received" else "→"
    if tx.risk_level == "high":
        out.append(Alert(user_id=user.id, transaction_id=tx.id, kind="HIGH_RISK", severity="high",
                         title="High-risk transaction detected", body=f"{amount} {arrow} {who}"))
    for p in (tx.risk or {}).get("components", {}).get("patterns", {}).get("items", []):
        if p["code"] in ALERT_PATTERNS:
            out.append(Alert(user_id=user.id, transaction_id=tx.id, kind=p["code"], severity=p["severity"],
                             title=p["title"], body=p["detail"]))
    db.add_all(out)
    return out


def related(db: Session, user: User, tx: Transaction, txs: list[Transaction]) -> dict:
    key = P.party(tx)
    same_party = [t for t in txs if t.id != tx.id and key and P.party(t) == key]
    window = [t for t in txs if t.id != tx.id and abs(t.occurred_at - tx.occurred_at) <= timedelta(hours=1)]
    return {"same_counterparty": same_party[-50:], "same_hour": window[-50:]}


def timeline(tx: Transaction, txs: list[Transaction], hours: int = 24) -> list[Transaction]:
    lo, hi = tx.occurred_at - timedelta(hours=hours), tx.occurred_at + timedelta(hours=hours)
    return [t for t in txs if lo <= t.occurred_at <= hi]


def rescore_all(db: Session, user: User, explain_ids: set[int] = frozenset()) -> list[Transaction]:
    """Score every transaction against the ones before it (one sort, then incremental prefixes)."""
    txs = history(db, user)
    for i, tx in enumerate(txs):
        score(db, tx, txs, explain=tx.id in explain_ids, prior=txs[:i])
    return txs

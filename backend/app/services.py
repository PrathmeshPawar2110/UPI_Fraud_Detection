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


def reporter_counts(db: Session, upis) -> dict[str, int]:
    """Distinct reporters for many UPI IDs in one query (bulk scoring)."""
    keys = {u.strip().lower() for u in upis if u}
    if not keys:
        return {}
    rows = db.execute(select(EntityReport.entity_value, func.count(func.distinct(EntityReport.user_id))).where(
        EntityReport.entity_type == "upi", EntityReport.entity_value.in_(keys), EntityReport.status != "REMOVED")
        .group_by(EntityReport.entity_value)).all()
    return {v: n for v, n in rows}


def score(db: Session, tx: Transaction, txs: list[Transaction] | None = None, explain: bool = True,
          prior: list[Transaction] | None = None, reporters: int | None = None) -> None:
    if reporters is None:
        reporters = reporter_count(db, tx.counterparty_upi)
    result = assess(tx, txs or [], reporters, explain=explain, prior=prior)
    old = dict(tx.risk or {})
    if old and {**old, "assessed_at": None} == {**result, "assessed_at": None}:
        return  # unchanged: don't write the row again (each UPDATE is a network round trip)
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


def rescore_all(db: Session, user: User, explain_ids: set[int] = frozenset(),
                new: list[Transaction] = ()) -> list[Transaction]:
    """Score every transaction against the ones before it (one sort, then incremental prefixes).

    `new` are transactions not yet added to the session: they're scored first and inserted with their
    scores in one batched INSERT, instead of INSERT + one UPDATE per row. Existing rows are only
    written when their score actually changed."""
    existing = history(db, user)
    order = {id(t): i for i, t in enumerate(new)}
    txs = sorted([*existing, *new], key=lambda t: (t.occurred_at, t.id if t.id is not None else 1 << 62, order.get(id(t), 0)))
    reports = reporter_counts(db, (t.counterparty_upi for t in txs))  # one query, not one per row
    for i, tx in enumerate(txs):
        key = (tx.counterparty_upi or "").strip().lower()
        score(db, tx, txs, explain=tx.id is not None and tx.id in explain_ids, prior=txs[:i],
              reporters=reports.get(key, 0))
    if new:
        db.add_all(new)
        db.flush()  # assigns ids (needed for alerts)
    return txs

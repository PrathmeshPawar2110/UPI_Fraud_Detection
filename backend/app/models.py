"""ORM models. Every user-owned row carries user_id, and every query filters on it.

Never stored: UPI PIN, OTP, bank passwords, card numbers/CVV. Passwords for UPI Guard accounts are
stored only as scrypt hashes.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80), default="")
    # ai_consent, notifications, demo_mode, retention_days
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Transaction(Base):
    """One payment from the user's point of view; the other party is the 'counterparty'."""
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(64))        # UTR / UPI reference
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # local time of the payment
    direction: Mapped[str] = mapped_column(String(10))                 # sent | received | cash_out
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    counterparty_name: Mapped[str | None] = mapped_column(String(120))
    counterparty_upi: Mapped[str | None] = mapped_column(String(120), index=True)
    payment_app: Mapped[str | None] = mapped_column(String(40))
    bank: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="success")
    balance_before: Mapped[float | None] = mapped_column(Float)
    balance_after: Mapped[float | None] = mapped_column(Float)
    receiver_balance_before: Mapped[float | None] = mapped_column(Float)
    receiver_balance_after: Mapped[float | None] = mapped_column(Float)
    device_id: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(280))
    received_answers: Mapped[dict | None] = mapped_column(JSON)       # knows_sender / in_bank / asked_to_pay
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual|screenshot|csv|demo|simulator|stream
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[float | None] = mapped_column(Float)            # unified score 0..1
    risk_level: Mapped[str | None] = mapped_column(String(10))         # low | medium | high
    risk: Mapped[dict | None] = mapped_column(JSON)                    # full breakdown (components, reasons, patterns)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed")  # unreviewed|legitimate|suspicious|confirmed_fraud
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


case_transactions = Table(
    "case_transactions", Base.metadata,
    Column("case_id", ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
    Column("transaction_id", ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(140))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")      # OPEN|INVESTIGATING|ESCALATED|RESOLVED|FALSE_POSITIVE
    priority: Mapped[str] = mapped_column(String(10), default="medium")  # low|medium|high
    resolution: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)          # [{type, label, data, added_at}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    transactions: Mapped[list[Transaction]] = relationship(secondary=case_transactions, lazy="selectin")


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EntityReport(Base):
    """A user's report about a UPI ID, phone number or URL. Unverified by design:
    other users only ever see aggregate counts by category, never the reporter or the description."""
    __tablename__ = "entity_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(10))   # upi | phone | url
    entity_value: Mapped[str] = mapped_column(String(300), index=True)  # normalised
    category: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float | None] = mapped_column(Float)
    incident_date: Mapped[str | None] = mapped_column(String(10))       # YYYY-MM-DD
    description: Mapped[str | None] = mapped_column(Text)              # private to the reporter
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING|REVIEWED|CONFIRMED_BY_USER|DISPUTED|REMOVED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)  # kept after account deletion on purpose
    action: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    success: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

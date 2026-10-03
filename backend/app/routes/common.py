"""Shared request/response models and helpers for the UPI Guard routes."""

import re
from datetime import datetime
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from ..engine import upi as U
from ..models import Transaction, User

Direction = Literal["sent", "received", "cash_out"]
Answer = Literal["yes", "no", "unsure"]
ReviewStatus = Literal["unreviewed", "legitimate", "suspicious", "confirmed_fraud"]
Source = Literal["manual", "screenshot", "csv", "demo", "simulator", "stream"]
REF_RE = re.compile(r"^[A-Za-z0-9-]{4,64}$")


class ReceivedAnswers(BaseModel):
    knows_sender: Optional[Answer] = None
    in_bank: Optional[Answer] = None
    asked_to_pay: Optional[Answer] = None


class TransactionIn(BaseModel):
    occurred_at: datetime
    direction: Direction
    amount: float = Field(gt=0, le=1e9, allow_inf_nan=False)
    counterparty_name: Optional[str] = Field(default=None, max_length=120)
    counterparty_upi: Optional[str] = Field(default=None, max_length=120)
    payment_app: Optional[str] = Field(default=None, max_length=40)
    bank: Optional[str] = Field(default=None, max_length=80)
    status: Literal["success", "failed", "pending"] = "success"
    external_id: Optional[str] = Field(default=None, max_length=64)
    balance_before: Optional[float] = Field(default=None, ge=0, le=1e10, allow_inf_nan=False)
    balance_after: Optional[float] = Field(default=None, ge=0, le=1e10, allow_inf_nan=False)
    receiver_balance_before: Optional[float] = Field(default=None, ge=0, le=1e10, allow_inf_nan=False)
    receiver_balance_after: Optional[float] = Field(default=None, ge=0, le=1e10, allow_inf_nan=False)
    device_id: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=80)
    category: Optional[str] = Field(default=None, max_length=40)
    note: Optional[str] = Field(default=None, max_length=280)
    received_answers: Optional[ReceivedAnswers] = None
    source: Source = "manual"

    @field_validator("counterparty_upi")
    @classmethod
    def valid_upi(cls, v):
        if v is None or not v.strip():
            return None
        if not U.is_valid(v):
            raise ValueError("UPI ID must look like name@handle.")
        return U.normalise(v)

    @field_validator("external_id")
    @classmethod
    def valid_ref(cls, v):
        if v is None or not v.strip():
            return None
        if not REF_RE.match(v.strip()):
            raise ValueError("Transaction reference may contain only letters, digits and dashes.")
        return v.strip()

    @field_validator("counterparty_name", "payment_app", "bank", "device_id", "location", "category", "note")
    @classmethod
    def strip_text(cls, v):
        v = (v or "").strip()
        return v or None

    @field_validator("occurred_at")
    @classmethod
    def naive_local(cls, v: datetime):
        return v.replace(tzinfo=None, microsecond=0)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_id: Optional[str]
    occurred_at: datetime
    direction: str
    amount: float
    currency: str
    counterparty_name: Optional[str]
    counterparty_upi: Optional[str]
    payment_app: Optional[str]
    bank: Optional[str]
    status: str
    balance_before: Optional[float]
    balance_after: Optional[float]
    receiver_balance_before: Optional[float]
    receiver_balance_after: Optional[float]
    device_id: Optional[str]
    location: Optional[str]
    category: Optional[str]
    note: Optional[str]
    received_answers: Optional[dict]
    source: str
    is_synthetic: bool
    risk_score: Optional[float]
    risk_level: Optional[str]
    review_status: str
    created_at: datetime


class TransactionDetail(TransactionOut):
    risk: Optional[dict]


def own_transaction(db: Session, user: User, tx_id: int) -> Transaction:
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.user_id != user.id:  # same 404 for "missing" and "not yours"
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return tx

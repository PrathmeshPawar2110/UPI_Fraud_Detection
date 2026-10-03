"""Request and response models for the API."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Transaction(BaseModel):
    type: Literal["TRANSFER", "CASH_OUT"]
    amount: float = Field(gt=0, allow_inf_nan=False)
    hour: int = Field(ge=0, le=23)
    sender_balance_before: float = Field(ge=0, allow_inf_nan=False)
    sender_balance_after: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    receiver_balance_before: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    receiver_balance_after: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def amount_within_balance(self):
        if self.amount > self.sender_balance_before + 1:
            raise ValueError("The amount is more than the balance before the payment. "
                             "Please check the balance (a UPI payment cannot exceed it).")
        return self


Answer = Literal["yes", "no", "unsure"]


class ReceivedPayment(BaseModel):
    """Money that came INTO the user's account. Scored with rules, not the model."""
    amount: float = Field(gt=0, allow_inf_nan=False)
    hour: int = Field(ge=0, le=23)
    knows_sender: Answer        # do you know the sender and expect this money?
    in_bank: Answer             # does the credit show in your bank app / bank SMS?
    asked_to_pay: Answer        # asked to return it, refund it, or pay a fee / deposit?


class Reason(BaseModel):
    text: str
    direction: Literal["up", "down"]


class Prediction(BaseModel):
    probability: Optional[float]  # None for the rule-based received-money check
    risk: Literal["low", "medium", "high"]
    meter: float
    reasons: list[Reason]
    used_receiver_balances: bool
    method: Literal["model", "rules"] = "model"

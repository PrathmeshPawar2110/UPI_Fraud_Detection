"""Deterministic pattern detectors over a user's transaction history.

Each detector looks only at transactions that happened at or before the one being scored, returns
a Pattern with the evidence it used, and never fires on too little history (MIN_HISTORY) for the
baseline-based checks. Codes double as fraud-event types (NEW_RECIPIENT, RAPID_TRANSFER, ...).

Weights are the pattern's contribution to the unified risk (see risk.py); they were set by hand to
reflect how strongly each pattern alone points to fraud, not learned from data.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Iterable, Protocol

MIN_HISTORY = 5          # new-recipient check needs this many earlier transactions
MIN_AMOUNT_HISTORY = 8   # unusual-amount baseline
MIN_HOUR_HISTORY = 10    # unusual-hour baseline
LARGE_AMOUNT = 100_000   # ₹1 lakh


class Tx(Protocol):
    id: Any
    occurred_at: datetime
    direction: str
    amount: float
    counterparty_upi: str | None
    counterparty_name: str | None
    balance_before: float | None
    device_id: str | None


@dataclass
class Pattern:
    code: str
    title: str
    detail: str
    weight: float
    severity: str                  # low | medium | high
    evidence: dict = field(default_factory=dict)
    informational: bool = False    # shown, but not added to the score (evidence already counted elsewhere)

    def to_dict(self) -> dict:
        return asdict(self)


def party(tx: Tx) -> str | None:
    key = (tx.counterparty_upi or tx.counterparty_name or "").strip().lower()
    return key or None


def outgoing(tx: Tx) -> bool:
    return tx.direction in ("sent", "cash_out")


def _inr(x: float) -> str:
    s = str(int(round(abs(x))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join([head[max(i - 2, 0):i] for i in range(len(head), 0, -2)][::-1])
        s = head + "," + tail
    return "₹" + s


def _quantile(values: list[float], q: float) -> float:
    v = sorted(values)
    if not v:
        return 0.0
    pos = (len(v) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def prior_of(tx: Tx, history: Iterable[Tx]) -> list[Tx]:
    """Transactions strictly before `tx` (ties broken by id), oldest first."""
    def before(h: Tx) -> bool:
        if h.occurred_at != tx.occurred_at:
            return h.occurred_at < tx.occurred_at
        return tx.id is not None and h.id is not None and h.id < tx.id
    return sorted((h for h in history if h is not tx and h.id != tx.id and before(h)), key=lambda h: h.occurred_at)


def baseline(prior: list[Tx]) -> dict:
    out_amounts = [h.amount for h in prior if outgoing(h)]
    hours = [h.occurred_at.hour for h in prior]
    common = sorted({h: hours.count(h) for h in set(hours)}.items(), key=lambda kv: -kv[1])[:3]
    return {
        "history_count": len(prior),
        "median_amount": round(median(out_amounts), 2) if out_amounts else None,
        "typical_range": [round(_quantile(out_amounts, 0.1), 2), round(_quantile(out_amounts, 0.9), 2)] if out_amounts else None,
        "common_hours": [h for h, _ in common],
        "known_counterparties": len({party(h) for h in prior if party(h)}),
    }


def detect(tx: Tx, history: Iterable[Tx], presorted: bool = False) -> list[Pattern]:
    """`presorted=True` means `history` is already exactly the earlier transactions, oldest first."""
    prior = list(history) if presorted else prior_of(tx, history)
    t, key = tx.occurred_at, party(tx)
    found: list[Pattern] = []

    # 1. Rapid transfers: 3+ outgoing payments within 5 minutes
    if outgoing(tx):
        window = [h for h in prior if outgoing(h) and h.occurred_at >= t - timedelta(minutes=5)] + [tx]
        if len(window) >= 3:
            total = sum(h.amount for h in window)
            found.append(Pattern(
                "RAPID_TRANSFER", "Rapid transfers",
                f"{len(window)} outgoing payments within 5 minutes, {_inr(total)} in total.",
                0.65 if total >= 50_000 else 0.5, "high" if total >= 50_000 else "medium",
                {"count": len(window), "total": round(total, 2), "window_minutes": 5}))

    # 6. Transaction burst: 6+ transactions of any kind within an hour (if rapid transfers didn't fire)
    if not any(p.code == "RAPID_TRANSFER" for p in found):
        hour_window = [h for h in prior if h.occurred_at >= t - timedelta(hours=1)] + [tx]
        if len(hour_window) >= 6:
            found.append(Pattern(
                "TRANSACTION_BURST", "Transaction burst",
                f"{len(hour_window)} transactions within one hour.", 0.35, "medium",
                {"count": len(hour_window), "window_minutes": 60}))

    # 2. Balance depletion: 90%+ of the balance sent
    if outgoing(tx) and tx.balance_before and tx.balance_before > 0 and tx.amount / tx.balance_before >= 0.9:
        share = tx.amount / tx.balance_before
        found.append(Pattern(
            "BALANCE_DEPLETION", "Possible balance depletion",
            f"Sends {share:.0%} of the {_inr(tx.balance_before)} balance.", 0.6, "high",
            {"share": round(share, 4), "balance_before": tx.balance_before}))

    # 3. New recipient (needs some history to know who is "new")
    if outgoing(tx) and key and len(prior) >= MIN_HISTORY and key not in {party(h) for h in prior}:
        found.append(Pattern(
            "NEW_RECIPIENT", "New recipient",
            f"First payment to {tx.counterparty_upi or tx.counterparty_name} in {len(prior)} earlier transactions.",
            0.25, "low", {"recipient": key, "history_count": len(prior)}))

    # 4. Unusual amount vs. the user's own outgoing payments
    out_prior = [h.amount for h in prior if outgoing(h)]
    if outgoing(tx) and len(out_prior) >= MIN_AMOUNT_HISTORY:
        med, p95 = median(out_prior), _quantile(out_prior, 0.95)
        if tx.amount > p95 and tx.amount >= 5 * med:
            lo, hi = _quantile(out_prior, 0.1), _quantile(out_prior, 0.9)
            found.append(Pattern(
                "UNUSUAL_AMOUNT", "Unusual amount",
                f"{_inr(tx.amount)} is {tx.amount / med:.0f}× your median payment; you normally pay {_inr(lo)}–{_inr(hi)}.",
                0.4, "medium", {"amount": tx.amount, "median": round(med, 2), "p95": round(p95, 2),
                                "typical_range": [round(lo, 2), round(hi, 2)]}))

    # 5. Unusual hour: a late-night payment at an hour the user almost never transacts
    if len(prior) >= MIN_HOUR_HISTORY and t.hour <= 5:
        near = sum(1 for h in prior if min((h.occurred_at.hour - t.hour) % 24, (t.hour - h.occurred_at.hour) % 24) <= 1)
        if near / len(prior) < 0.05:
            found.append(Pattern(
                "UNUSUAL_HOUR", "Unusual time",
                f"Made at {t:%H:%M}; only {near} of your {len(prior)} earlier transactions were around this hour.",
                0.3, "medium", {"hour": t.hour, "nearby_count": near, "history_count": len(prior)}))

    # 7. Recipient concentration: 3+ payments in 24 h to someone first paid within those 24 h
    if outgoing(tx) and key:
        to_key = [h for h in prior if party(h) == key]
        first_seen = to_key[0].occurred_at if to_key else t
        if first_seen >= t - timedelta(hours=24):
            recent = [h for h in to_key if outgoing(h) and h.occurred_at >= t - timedelta(hours=24)] + [tx]
            if len(recent) >= 3:
                found.append(Pattern(
                    "RECIPIENT_CONCENTRATION", "Repeated payments to a new recipient",
                    f"{len(recent)} payments in 24 hours to a recipient first paid {_ago(t - first_seen)} ago, "
                    f"{_inr(sum(h.amount for h in recent))} in total.",
                    0.5, "high", {"count": len(recent), "total": round(sum(h.amount for h in recent), 2)}))

    # 8. Refund loop (circular movement): paying someone who just paid you
    if outgoing(tx) and key:
        paid_us = [h for h in prior if h.direction == "received" and party(h) == key
                   and h.occurred_at >= t - timedelta(hours=72)]
        if paid_us:
            got = sum(h.amount for h in paid_us)
            found.append(Pattern(
                "REFUND_LOOP", "Money sent back to a recent sender",
                f"This recipient sent you {_inr(got)} in the last 72 hours. Returning a 'wrong transfer' or "
                "'refund' yourself is how these scams take money.",
                0.45, "medium", {"received_total": round(got, 2), "received_count": len(paid_us)}))

    # New device (only when devices are recorded, e.g. simulator or imported data)
    devices = {h.device_id for h in prior if h.device_id}
    if tx.device_id and len(devices) >= 1 and len(prior) >= 3 and tx.device_id not in devices:
        found.append(Pattern(
            "NEW_DEVICE", "New device", f"First transaction from device {tx.device_id}.", 0.35, "medium",
            {"device_id": tx.device_id, "known_devices": len(devices)}))

    # Large absolute amount (weak on its own)
    if outgoing(tx) and tx.amount >= LARGE_AMOUNT:
        found.append(Pattern(
            "LARGE_AMOUNT", "Large amount", f"{_inr(tx.amount)} is above ₹1,00,000.", 0.2, "low",
            {"amount": tx.amount, "threshold": LARGE_AMOUNT}))

    return found


def _ago(d: timedelta) -> str:
    minutes = int(d.total_seconds() // 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h"

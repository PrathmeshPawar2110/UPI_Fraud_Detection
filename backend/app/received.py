"""Rule-based check for money the user RECEIVED.

The LightGBM model only learned outgoing account-takeover fraud (PaySim has no labelled incoming
scams), so incoming payments are judged with transparent rules built on the common UPI scams
that involve money arriving in your account:
- fake "payment received" screenshots, where no money actually arrived
- "sent by mistake, please return it" (the original credit is often stolen or later reversed)
- task / job / investment scams that pay a small amount first, then ask you to pay in
- unexplained credits from strangers, which can be stolen money and get your account frozen

Receiving money cannot by itself take money out of your account, so an unexpected credit from a
stranger is "medium" rather than "high" unless a stronger scam sign is present.
"""

from .fraud import inr, hour_label
from .schemas import ReceivedPayment

LARGE_AMOUNT = 50_000
METER = {"low": 1 / 6, "medium": 1 / 2, "high": 5 / 6}


def check_received(p: ReceivedPayment) -> dict:
    reasons = []  # (text, direction, weight)
    risk = "low"

    def raise_to(level: str):
        nonlocal risk
        if ["low", "medium", "high"].index(level) > ["low", "medium", "high"].index(risk):
            risk = level

    if p.in_bank == "no":
        raise_to("high")
        reasons.append(("The money does not show in your bank account. Fake \"payment received\" screenshots are a "
                        "common scam to get goods or a refund out of you.", "up", 3))
    elif p.in_bank == "unsure":
        raise_to("medium")
        reasons.append(("Check your bank app or bank SMS, not just the screenshot. A screenshot alone does not prove "
                        "the money arrived.", "up", 1))

    if p.asked_to_pay == "yes":
        raise_to("high")
        reasons.append(("Someone asked you to send money back, refund it, or pay a fee or deposit. Scammers send a "
                        "small amount first, then ask for more, or claim a \"wrong transfer\" so you return it to "
                        "a different account.", "up", 3))

    if p.knows_sender == "no":
        raise_to("medium")
        reasons.append(("You do not know the sender. Unexpected money from a stranger can be stolen funds, and if "
                        "the source is reported your account can be frozen.", "up", 2))
        if p.amount >= LARGE_AMOUNT:
            raise_to("high")
            reasons.append((f"{inr(p.amount)} is a large unexplained credit. Mule accounts that pass on stolen "
                            "money usually receive amounts like this from strangers.", "up", 2))
    elif p.knows_sender == "unsure":
        raise_to("medium")
        reasons.append(("You are not sure who sent it. Confirm with the sender on a number you already have, not "
                        "one given in a message.", "up", 1))
    else:
        reasons.append(("You know the sender and were expecting this money.", "down", 1))

    if p.knows_sender != "yes" and p.hour <= 5:
        reasons.append((f"Received around {hour_label(p.hour)}. Scam credits are often sent late at night.", "up", 1))

    if risk == "low":
        reasons.append(("Receiving money never needs your UPI PIN. If anyone asks for it to \"receive\" a payment, "
                        "it is a scam.", "down", 0))

    reasons.sort(key=lambda r: -r[2])
    return {
        "probability": None,
        "risk": risk,
        "meter": METER[risk],
        "reasons": [{"text": t, "direction": d} for t, d, _ in reasons[:4]],
        "used_receiver_balances": False,
        "method": "rules",
    }

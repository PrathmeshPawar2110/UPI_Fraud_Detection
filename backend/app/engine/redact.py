"""Mask secrets before anything is stored as evidence: OTPs, PINs, CVVs and card numbers."""

import re

SECRET_NEAR = re.compile(r"(?i)\b(otp|o\.t\.p|one[- ]time password|upi pin|mpin|pin|cvv|cvc|password|passcode)\b([^0-9\n]{0,20})(\d{3,8})")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def redact(text: str) -> str:
    if not text:
        return text
    out = SECRET_NEAR.sub(lambda m: m.group(1) + m.group(2) + "•" * len(m.group(3)), text)
    return CARD.sub(lambda m: "•••• " + re.sub(r"\D", "", m.group(0))[-4:] if len(re.sub(r"\D", "", m.group(0))) >= 13 else m.group(0), out)


def redact_obj(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_obj(v) for k, v in value.items()}
    return value

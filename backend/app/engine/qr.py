"""QR / UPI-link payload analysis. The QR image is decoded in the browser (jsQR); only the decoded
text reaches the server.

UPI deep-link format (NPCI linking specification): upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR
&tn=<note>&tr=<ref>&mc=<merchant code>&mode=<initiation mode>
"""

import re
from urllib.parse import parse_qsl, urlsplit

from . import upi as U
from . import urls as URL
from .risk import level_of, noisy_or

RECEIVE_WORDS = re.compile(r"\b(refund|cashback|receive|reward|prize|kyc|winner|lottery|bonus|claim|return)\b", re.I)


def parse_upi(payload: str) -> dict | None:
    if not payload.lower().startswith("upi:"):
        return None
    parts = urlsplit(payload.strip())
    params = {k.lower(): v.strip() for k, v in parse_qsl(parts.query, keep_blank_values=True)}
    action = (parts.netloc or parts.path.strip("/")).lower()
    return {"action": action, "params": params}


def analyze(payload: str, known_party: bool | None = None, reports: int = 0) -> dict:
    text = (payload or "").strip()[:2000]
    upi = parse_upi(text)
    if upi is None:
        if re.match(r"^(https?://|www\.)", text, re.I):
            r = URL.analyze(text)
            return {"kind": "url", "level": {"HIGH RISK": "high", "SUSPICIOUS": "medium", "SAFE": "low"}.get(r["verdict"], "unknown"),
                    "summary": f"This QR opens a web link. {r['summary']}", "payment": None,
                    "warnings": [s for s in r["signals"] if s["kind"] != "good"], "url": r}
        return {"kind": "text", "level": "unknown", "payment": None, "warnings": [],
                "summary": "This QR contains plain text, not a UPI payment."}

    p = upi["params"]
    vpa = U.normalise(p.get("pa", ""))
    amount = None
    try:
        amount = float(p["am"]) if p.get("am") else None
    except ValueError:
        pass
    payment = {"payee_vpa": vpa or None, "payee_name": p.get("pn") or None, "amount": amount,
               "currency": p.get("cu") or "INR", "note": p.get("tn") or None, "reference": p.get("tr") or None,
               "merchant_code": p.get("mc") or None, "action": upi["action"]}
    warnings = []

    def warn(code, weight, msg):
        warnings.append({"code": code, "weight": weight, "text": msg})

    if upi["action"] not in ("pay",):
        warn("NOT_PAY", 0.45, f"This is a UPI '{upi['action']}' link, not a simple payment. Read every screen before approving.")
    info = U.inspect(vpa) if vpa else None
    if not vpa or not info["valid"]:
        warn("BAD_VPA", 0.75, "The payee UPI ID is missing or invalid. Don't pay with this QR.")
    else:
        payment.update({"app": info["app"], "bank": info["bank"]})
        for s in info["signals"]:
            if s["severity"] == "medium":
                warn("PAYEE_NAME_LURE", 0.4, s["text"])
    if payment["payee_name"] and RECEIVE_WORDS.search(payment["payee_name"]):
        warn("NAME_LURE", 0.4, f"The payee name '{payment['payee_name']}' sounds like a refund/reward. Businesses don't name themselves that way.")
    if payment["note"] and RECEIVE_WORDS.search(payment["note"]):
        warn("RECEIVE_TRICK", 0.6, f"The note says '{payment['note']}'. Scanning a QR always SENDS money; "
                                    "no one can pay you by asking you to scan.")
    if payment["currency"].upper() != "INR":
        warn("CURRENCY", 0.2, f"Currency is {payment['currency']}; UPI uses INR only.")
    if amount:
        warn("PREFILLED", 0.25 if amount >= 50_000 else 0.1,
             f"The amount ₹{amount:,.0f} is pre-filled. Make sure it's what you agreed to pay.")
    if known_party is False:
        warn("NEW_RECIPIENT", 0.15, "You haven't paid this UPI ID before (in your UPI Guard history).")
    if reports:
        warn("REPORTED", min(0.2 + 0.1 * (reports - 1), 0.45), f"Reported by {reports} UPI Guard user{'s' if reports > 1 else ''} (unverified).")

    score = noisy_or(w["weight"] for w in warnings)
    level = level_of(score) if warnings else "low"
    return {"kind": "upi", "level": level, "score": round(score, 3), "payment": payment, "warnings": warnings,
            "summary": {"high": "Strong warning signs. Don't pay with this QR.",
                        "medium": "Check the warnings before paying.",
                        "low": "No strong warning signs. Confirm the payee name in your app before approving."}[level]}

"""UPI ID (VPA) validation, payment-app handle lookup and name-based warning signs.

The handle table covers well-known handles only (best effort, not an official NPCI list): an unknown
handle is not evidence of fraud, new handles appear regularly.
"""

import re

VPA_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,255}@[a-z][a-z0-9]{1,63}$")

HANDLES = {
    # PhonePe
    "ybl": ("PhonePe", "Yes Bank"), "ibl": ("PhonePe", "ICICI Bank"), "axl": ("PhonePe", "Axis Bank"),
    # Google Pay
    "okaxis": ("Google Pay", "Axis Bank"), "okhdfcbank": ("Google Pay", "HDFC Bank"),
    "okicici": ("Google Pay", "ICICI Bank"), "oksbi": ("Google Pay", "State Bank of India"),
    # Paytm
    "paytm": ("Paytm", "Paytm Payments Bank"), "ptyes": ("Paytm", "Yes Bank"), "ptaxis": ("Paytm", "Axis Bank"),
    "pthdfc": ("Paytm", "HDFC Bank"), "ptsbi": ("Paytm", "State Bank of India"),
    # Others
    "upi": ("BHIM", "NPCI BHIM"), "apl": ("Amazon Pay", "Axis Bank"), "yapl": ("Amazon Pay", "Yes Bank"),
    "rapl": ("Amazon Pay", "RBL Bank"), "waicici": ("WhatsApp Pay", "ICICI Bank"),
    "wahdfcbank": ("WhatsApp Pay", "HDFC Bank"), "waaxis": ("WhatsApp Pay", "Axis Bank"),
    "wasbi": ("WhatsApp Pay", "State Bank of India"), "ikwik": ("MobiKwik", "MobiKwik"),
    "freecharge": ("Freecharge", "Axis Bank"), "airtel": ("Airtel Thanks", "Airtel Payments Bank"),
    # Bank apps
    "sbi": ("Bank app", "State Bank of India"), "hdfcbank": ("Bank app", "HDFC Bank"),
    "icici": ("Bank app", "ICICI Bank"), "axisbank": ("Bank app", "Axis Bank"), "kotak": ("Bank app", "Kotak Mahindra Bank"),
    "pnb": ("Bank app", "Punjab National Bank"), "barodampay": ("Bank app", "Bank of Baroda"),
    "idfcbank": ("Bank app", "IDFC First Bank"), "yesbank": ("Bank app", "Yes Bank"),
}

# Words scammers put in UPI IDs to look official or to promise money.
LURE_WORDS = ["kyc", "refund", "support", "care", "helpdesk", "helpline", "customer", "service", "verify",
              "verification", "reward", "cashback", "lottery", "prize", "winner", "rbi", "npci", "sbi", "hdfc",
              "icici", "axis", "paytm", "phonepe", "gpay", "official", "govt", "income", "tax", "electricity", "bill"]


def normalise(vpa: str) -> str:
    return (vpa or "").strip().lower()


def is_valid(vpa: str) -> bool:
    return bool(VPA_RE.match(normalise(vpa)))


def inspect(vpa: str) -> dict:
    v = normalise(vpa)
    valid = bool(VPA_RE.match(v))
    local, _, handle = v.partition("@")
    app, bank = HANDLES.get(handle, (None, None)) if valid else (None, None)  # don't vouch for malformed IDs
    signals = []
    if not valid:
        signals.append({"code": "INVALID_FORMAT", "severity": "high",
                        "text": "This is not a valid UPI ID format (name@handle, letters/digits/._- only)."})
    else:
        if handle not in HANDLES:
            signals.append({"code": "UNKNOWN_HANDLE", "severity": "info",
                            "text": f"'@{handle}' is not in our list of well-known handles. That alone is not a warning sign."})
        # Long words as substrings ("kycupdate" style IDs have no separators); short ones only as whole
        # tokens, so ordinary names ("oscar", "taxila") don't trigger.
        tokens = set(re.split(r"[._\-0-9]+", local))
        lures = [w for w in LURE_WORDS if (len(w) >= 5 and w in local) or w in tokens
                 or (w == "kyc" and "kyc" in local)]
        if lures:
            signals.append({"code": "LURE_WORDS", "severity": "medium",
                            "text": f"The ID contains '{', '.join(lures[:3])}'. Scammers use words like these to look "
                                    "official or promise refunds. Banks and NPCI never ask you to pay to a UPI ID to "
                                    "get a refund, reward or KYC update."})
        if re.fullmatch(r"[6-9]\d{9}", local):
            signals.append({"code": "MOBILE_NUMBER", "severity": "info",
                            "text": "The ID is a mobile number. Check the name your app shows before paying."})
    return {"vpa": v, "valid": valid, "local": local, "handle": handle, "app": app, "bank": bank,
            "signals": signals}

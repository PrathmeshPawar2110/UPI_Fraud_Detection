"""Suspicious SMS / WhatsApp message scanner (English, Hinglish and common Hindi/Marathi words).

Rule-based: each indicator has a category, a weight and a plain explanation. Links in the message are
checked with the URL heuristics. No indicator -> "no known scam indicators", never "safe".
"""

import re

from . import upi as U
from . import urls as URL
from .risk import level_of, noisy_or

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"]+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|net|org|xyz|top|ly|co|info|live|site|online|shop|click|me|io)(?:/[^\s]*)?",
                    re.IGNORECASE)
UPI_RE = re.compile(r"\b[a-z0-9][a-z0-9._-]{1,60}@[a-z][a-z0-9]{1,30}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr)\s?([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE)
BRANDS = ["SBI", "HDFC", "ICICI", "Axis", "Kotak", "PNB", "Bank of Baroda", "Paytm", "PhonePe", "Google Pay", "GPay",
          "BHIM", "NPCI", "RBI", "Income Tax", "UIDAI", "Aadhaar", "EPFO", "TRAI", "FedEx", "DHL", "Blue Dart",
          "Customs", "CBI", "Police", "Electricity", "Amazon", "Flipkart", "KBC"]

# (code, category, weight, explanation, patterns)
INDICATORS = [
    ("CREDENTIAL_REQUEST", "OTP / PIN theft", 0.75,
     "Asks for an OTP, UPI PIN, CVV or password. No bank, app or official ever asks for these.",
     [r"\b(share|send|tell|give|forward|enter|provide|bhejo|batao|bata do|de do)\b.{0,25}\b(otp|o\.t\.p|pin|mpin|cvv|password)\b",
      r"\b(otp|upi pin|mpin|cvv|password)\b.{0,25}\b(share|send|tell|bhejo|batao|bata|de do|bhej)\b",
      r"ओटीपी.{0,20}(भेज|बता|शेयर)", r"(पिन|पासवर्ड).{0,20}(भेज|बता)"]),
    ("RECEIVE_PIN_TRICK", "Receive-money trick", 0.7,
     "Says you must scan, approve or enter your PIN to RECEIVE money. UPI never needs a PIN to receive.",
     [r"\b(scan|approve|accept|enter pin|pin daal|pin dal)\b.{0,40}\b(receive|get|credit|refund|cashback|prize)\b",
      r"\b(receive|get|credit)\b.{0,30}\b(enter|put|daal|dal)\b.{0,10}\bpin\b"]),
    ("KYC_THREAT", "KYC / account-block scam", 0.5,
     "Threatens to block your account or SIM unless you 'update KYC'. Banks don't do KYC through SMS links.",
     [r"\bkyc\b.{0,40}\b(update|expire|expired|pending|block|suspend|band|verify|complete)",
      r"\b(update|complete|verify)\b.{0,20}\bkyc\b", r"केवाईसी", r"\bpan\b.{0,20}\b(link|update)\b.{0,30}\b(block|suspend)"]),
    ("ACCOUNT_THREAT", "Urgency / threat", 0.35,
     "Creates panic: account, card or SIM 'will be blocked' or 'disconnected'. Pressure is a scam tactic.",
     [r"\b(will be|has been|is|are|get)\s+(blocked|suspended|deactivated|closed|disconnected|frozen)\b",
      r"\b(band ho jayega|band ho jaega|block ho jayega|bandh)\b", r"खाता.{0,15}बंद", r"खाते.{0,15}बंद",
      r"\b(disconnect|disconnection)\b.{0,40}\b(tonight|today|9:30|10:30|immediately)\b"]),
    ("URGENCY", "Urgency / threat", 0.2,
     "Demands immediate action ('urgent', 'within 24 hours', 'last warning').",
     [r"\b(urgent|immediately|within \d+ (hours|hrs|minutes|mins)|last warning|final notice|act now|turant|jaldi)\b"]),
    ("PRIZE", "Prize / lottery scam", 0.45,
     "Promises a prize, lottery or cashback you didn't apply for, usually with a 'processing fee'.",
     [r"\b(you have won|you won|lottery|lucky draw|prize money|jackpot|kbc|winner|congratulations.{0,20}(won|selected))\b",
      r"इनाम", r"लॉटरी"]),
    ("WRONG_TRANSFER", "Wrong-transfer / refund scam", 0.5,
     "Claims money was sent to you by mistake and asks you to return it. Genuine mistakes are reversed by the bank.",
     [r"\b(wrong(ly)? (transfer|sent)|sent by mistake|by mistake|galti se|galati se|return (the|my) money|wapas (bhej|kar))\b"]),
    ("REMOTE_ACCESS", "Remote-access scam", 0.7,
     "Asks you to install a screen-sharing app (AnyDesk, TeamViewer, QuickSupport). This gives them control of your phone.",
     [r"\b(anydesk|any desk|teamviewer|team viewer|quicksupport|quick support|rustdesk|airdroid|screen ?share)\b"]),
    ("TASK_JOB", "Job / task scam", 0.45,
     "Offers easy money for tasks (liking videos, reviews, part-time work), later asks you to 'invest' to withdraw.",
     [r"\b(work from home|part[- ]time job|daily (income|earning)|earn ₹?\s?\d+.{0,20}(daily|per day|per task)|like (videos|youtube)|rate (hotels|products)|telegram task)\b"]),
    ("INVESTMENT", "Investment scam", 0.45,
     "Promises guaranteed or very high returns. Real investments never guarantee returns.",
     [r"\b(guaranteed (return|profit)|double (your|the) money|\d{2,3}% (return|profit)|crypto (trading|signals)|stock tips|ipo allotment|vip trading group)\b"]),
    ("IMPERSONATION_AUTHORITY", "Digital-arrest / impersonation", 0.6,
     "Claims to be police, CBI, customs or a courier about illegal parcels. Officials never 'arrest' you over a call or ask for money.",
     [r"\b(digital arrest|cbi|narcotics|customs officer|cyber cell|police station)\b",
      r"\b(parcel|courier|package)\b.{0,40}\b(drugs|illegal|seized|customs)\b"]),
    ("BILL_DISCONNECT", "Bill-payment scam", 0.45,
     "Says your electricity/gas will be cut tonight and gives a number to call. Pay bills only in official apps.",
     [r"\belectricity\b.{0,60}\b(disconnect|cut|tonight|today)\b", r"\b(bijli|light).{0,30}(kat|cut)"]),
    ("CALL_BACK", "Contact pressure", 0.15,
     "Asks you to call or WhatsApp an unknown number.",
     [r"\b(call|contact|whatsapp|whats app|sampark)\b.{0,20}(\+?91[\s-]?)?[6-9]\d{9}"]),
]


def analyze(text: str) -> dict:
    t = (text or "")[:5000]
    lower = t.lower()
    hits = []
    for code, category, weight, why, pats in INDICATORS:
        if any(re.search(p, lower) for p in pats):
            hits.append({"code": code, "category": category, "weight": weight, "text": why})

    links = []
    for m in URL_RE.findall(t)[:5]:
        r = URL.analyze(m)
        if r["verdict"] in ("HIGH RISK", "SUSPICIOUS"):
            hits.append({"code": "SUSPICIOUS_LINK", "category": "Phishing link", "weight": min(r["score"], 0.6),
                         "text": f"The link {r['input'][:60]} is {r['verdict'].lower()}: {r['signals'][0]['text'] if r['signals'] else ''}"})
        elif r["verdict"] != "SAFE":
            hits.append({"code": "LINK", "category": "Phishing link", "weight": 0.15,
                         "text": f"Contains a link ({r['input'][:60]}). Don't pay or log in through links in messages."})
        links.append({"url": r["input"], "verdict": r["verdict"]})

    brands = [b for b in BRANDS if re.search(r"\b" + re.escape(b.lower()) + r"\b", lower)]
    if brands and any(h["code"] in ("KYC_THREAT", "ACCOUNT_THREAT", "CREDENTIAL_REQUEST", "SUSPICIOUS_LINK", "LINK")
                      for h in hits):
        hits.append({"code": "IMPERSONATION", "category": "Impersonation", "weight": 0.2,
                     "text": f"Uses the name {brands[0]} together with a threat or link, a common impersonation pattern."})

    score = noisy_or(h["weight"] for h in hits)
    level = level_of(score) if hits else "low"
    categories = {}
    for h in hits:
        categories[h["category"]] = max(categories.get(h["category"], 0), h["weight"])
    likely = sorted(categories, key=lambda c: -categories[c])[:2]

    return {
        "level": level,
        "score": round(score, 3),
        "likely_scam": likely,
        "summary": ("No known scam indicators found. Still, never share OTP/PIN and verify senders independently."
                    if not hits else f"{'High-risk' if level == 'high' else 'Possible'} scam: {', '.join(likely)}."),
        "indicators": hits,
        "extracted": {
            "urls": links,
            "upi_ids": sorted({u.lower() for u in UPI_RE.findall(t) if U.is_valid(u)})[:5],
            "phones": sorted({re.sub(r"[\s-]", "", p) for p in PHONE_RE.findall(t)})[:5],
            "amounts": [float(a.replace(",", "")) for a in AMOUNT_RE.findall(t)][:5],
            "brands": brands[:5],
        },
    }

"""Next-step guidance shared by the emergency page, investigation and incident reports.

Official channels (verified Oct 2026):
- 1930 / cybercrime.gov.in: National Cyber Crime Reporting Portal, for money already lost
- Sanchar Saathi "Chakshu": suspected fraud calls/SMS/WhatsApp (no money lost)
- RBI Complaint Management System (cms.rbi.org.in): if the bank doesn't resolve a complaint
The app can't block accounts or recover money itself; it only points to these channels.
"""

RESOURCES = [
    {"name": "National Cyber Crime Helpline", "contact": "1930", "url": "tel:1930",
     "when": "You have lost money. Call as soon as possible, fast reports improve the chance of freezing funds."},
    {"name": "National Cyber Crime Reporting Portal", "contact": "cybercrime.gov.in", "url": "https://cybercrime.gov.in",
     "when": "File a complaint with the transaction ID / UTR, screenshots and the scammer's UPI ID or number."},
    {"name": "Sanchar Saathi – Chakshu", "contact": "sancharsaathi.gov.in", "url": "https://sancharsaathi.gov.in",
     "when": "Report a suspected fraud call, SMS or WhatsApp message (when no money was lost)."},
    {"name": "RBI Complaint Management System", "contact": "cms.rbi.org.in", "url": "https://cms.rbi.org.in",
     "when": "Escalate if your bank doesn't resolve your complaint within 30 days."},
]

EMERGENCY_STEPS = [
    {"title": "Stop further payments", "text": "Don't approve any more requests or scan any QR. Block UPI in your bank app or by calling your bank."},
    {"title": "Preserve the evidence", "text": "Keep screenshots, the transaction ID / UTR, the scammer's UPI ID, number, messages and links. Don't delete chats."},
    {"title": "Contact your bank", "text": "Call the number on the back of your card or in the official app, report the transaction and ask them to raise a dispute."},
    {"title": "Report the fraud", "text": "Call 1930 and file a complaint on cybercrime.gov.in. Ask for the acknowledgement number."},
    {"title": "Secure your accounts", "text": "Change your UPI PIN and passwords, remove unknown devices, uninstall screen-sharing apps (AnyDesk, TeamViewer)."},
]


def next_steps(level: str, lost_money: bool, has_messages: bool = False) -> list[str]:
    steps = []
    if lost_money and level in ("medium", "high"):
        steps += ["Call 1930 now and report the transaction (have the UTR ready).",
                  "Call your bank to block UPI and dispute the transaction.",
                  "File a complaint at cybercrime.gov.in and keep the acknowledgement number."]
    elif level in ("medium", "high"):
        steps += ["Don't send any more money to this recipient until you have verified them independently.",
                  "If you didn't make this payment, call your bank and 1930 immediately."]
    if has_messages:
        steps.append("Report the scam message or call on Sanchar Saathi (Chakshu).")
    steps.append("Never share your UPI PIN or OTP. You never need a PIN to receive money.")
    return steps

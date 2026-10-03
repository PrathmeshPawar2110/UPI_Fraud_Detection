"""Fraud scenario simulator and synthetic data. ALL DATA HERE IS SYNTHETIC: names, UPI IDs and
amounts are invented; '.example' domains never resolve.

Each scenario is a scripted sequence of events played against a synthetic "normal" history. Every
event is evaluated by the same engines the app uses for real input:
- payments          -> risk.assess (ML model + rules + patterns)
- SMS / chat text   -> message.analyze
- links             -> urls.analyze
- QR payloads       -> qr.analyze
Nothing in a scenario says "this is fraud"; the detections come from the engines.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import count

from . import message as M, qr as Q, urls as URL
from .risk import assess, level_of

SYNTHETIC_LABEL = "SYNTHETIC DEMO DATA — NOT REAL BANK DATA"
HOME_DEVICE = "android-7f3a"

# Everyday payees for the normal baseline (invented).
NORMAL_PAYEES = [
    ("Sharma General Store", "sharmastore@ybl", "groceries", (120, 1800)),
    ("Fresh Mart", "freshmart.blr@okaxis", "groceries", (300, 2500)),
    ("Ravi Auto", "ravi.auto77@paytm", "transport", (60, 400)),
    ("City Pharmacy", "citypharma@okhdfcbank", "health", (150, 1200)),
    ("Chai Point", "chaipoint.ka@ybl", "food", (40, 250)),
    ("Ananya (flatmate)", "ananya.k@oksbi", "friends", (500, 6000)),
    ("Metro Recharge", "metrocard@upi", "transport", (200, 1000)),
]
BILLS = [("StreamFlix", "streamflix@ybl", 649, 5), ("TuneBox Music", "tunebox@okicici", 119, 12),
         ("BESCOM Electricity", "bescom.bill@okaxis", 1450, 8), ("Airtel Postpaid", "airtelbill@airtel", 599, 20)]


@dataclass
class SimTx:
    id: int
    occurred_at: datetime
    direction: str
    amount: float
    counterparty_name: str | None = None
    counterparty_upi: str | None = None
    balance_before: float | None = None
    balance_after: float | None = None
    receiver_balance_before: float | None = None
    receiver_balance_after: float | None = None
    device_id: str | None = HOME_DEVICE
    location: str | None = "Bengaluru"
    category: str | None = None
    payment_app: str | None = "PhonePe"
    received_answers: dict | None = None
    note: str | None = None
    status: str = "success"
    extra: dict = field(default_factory=dict)


def baseline_history(end: datetime, days: int = 45, seed: int = 7, start_balance: float = 85_000) -> tuple[list[SimTx], float]:
    """Synthetic normal activity: daytime payments, monthly salary and bills. Returns (txs, balance)."""
    rng = random.Random(seed)
    ids = count(1)
    txs, balance = [], start_balance
    start = (end - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    for d in range(days):
        day = start + timedelta(days=d)
        if day.day == 1:
            txs.append(SimTx(next(ids), day.replace(hour=10, minute=5), "received", 62_000.0, "Acme Tech Pvt Ltd",
                             "payroll.acme@hdfcbank", category="salary", payment_app="Bank app"))
            balance += 62_000
        for name, vpa, amount, dom in BILLS:
            if day.day == dom:
                t = day.replace(hour=rng.randint(9, 20), minute=rng.randint(0, 59))
                txs.append(SimTx(next(ids), t, "sent", float(amount), name, vpa, balance, balance - amount, category="bills"))
                balance -= amount
        for _ in range(rng.choice([0, 1, 1, 2, 2, 3])):
            name, vpa, cat, (lo, hi) = rng.choice(NORMAL_PAYEES)
            amount = float(round(rng.uniform(lo, hi), -1) or lo)
            t = day.replace(hour=rng.randint(8, 22), minute=rng.randint(0, 59))
            txs.append(SimTx(next(ids), t, "sent", amount, name, vpa, balance, balance - amount, category=cat))
            balance -= amount
    txs.sort(key=lambda x: x.occurred_at)
    # recompute running balances in time order
    bal = start_balance
    for i, t in enumerate(txs):
        t.id = i + 1
        if t.direction == "received":
            bal += t.amount
        else:
            t.balance_before, t.balance_after = bal, max(bal - t.amount, 0.0)
            bal = t.balance_after
    return txs, bal


# ---------- scenarios ----------

def _scenarios() -> dict:
    return {
        "account_takeover": {
            "title": "Account takeover",
            "summary": "A fraudster gets into the account from a new phone, adds a beneficiary and drains it in minutes.",
            "steps": [
                (0, "event", {"title": "Login from a new device", "detail": "SIM-swapped phone 'iphone-x91' signs in at 00:41.", "device": "iphone-x91"}),
                (2, "event", {"title": "New beneficiary added", "detail": "quickpay.mule01@axl added as a payee."}),
                (3, "tx", {"amount": 50_000, "to": ("Rahul Traders", "quickpay.mule01@axl"), "device": "iphone-x91"}),
                (4, "tx", {"amount": 40_000, "to": ("Rahul Traders", "quickpay.mule01@axl"), "device": "iphone-x91"}),
                (5, "tx", {"amount": "rest", "to": ("Swift Wallet Svc", "swiftwallet.cash@ibl"), "device": "iphone-x91", "cash_out": True}),
            ]},
        "fake_refund": {
            "title": "Fake refund",
            "summary": "A 'support agent' promises a refund and sends a QR that actually takes money.",
            "steps": [
                (0, "message", {"text": "Dear customer, your refund of Rs 4,999 for order #88214 is approved. Scan the QR sent on WhatsApp and enter UPI PIN to receive the refund immediately."}),
                (3, "qr", {"payload": "upi://pay?pa=refund.desk24@ybl&pn=Refund%20Desk&am=4999&cu=INR&tn=Receive%20refund"}),
                (4, "tx", {"amount": 4_999, "to": ("Refund Desk", "refund.desk24@ybl")}),
            ]},
        "kyc_scam": {
            "title": "KYC scam",
            "summary": "An SMS threatens to block the account unless KYC is updated through a link.",
            "steps": [
                (0, "message", {"text": "SBI: Dear user your account will be blocked today due to pending KYC. Update KYC immediately: http://sbi-kyc-update.example/verify or call 9876543210"}),
                (1, "url", {"url": "http://sbi-kyc-update.example/verify?acc=kyc"}),
                (6, "message", {"text": "Sir to complete KYC please share the OTP you received and install AnyDesk for verification."}),
                (9, "tx", {"amount": 24_500, "to": ("KYC Verification Cell", "kyc.verify.cell@ybl"), "new_device": False}),
            ]},
        "wrong_transfer": {
            "title": "Wrong-transfer scam",
            "summary": "A stranger 'accidentally' sends money, then pressures you to return it.",
            "steps": [
                (0, "rx", {"amount": 5_000, "from": ("Unknown Sender", "mohit.k1990@okaxis"),
                           "answers": {"knows_sender": "no", "in_bank": "unsure", "asked_to_pay": "yes"}}),
                (12, "message", {"text": "Bhai galti se 5000 aapke account me chale gaye, please wapas bhej do urgent, mera hospital ka payment hai"}),
                (20, "tx", {"amount": 5_000, "to": ("Unknown Sender", "mohit.k1990@okaxis")}),
            ]},
        "fake_support": {
            "title": "Fake customer support",
            "summary": "A number found online as 'customer care' asks for remote access, then a 'verification' payment.",
            "steps": [
                (0, "message", {"text": "Thank you for contacting PhonePe Customer Care. To resolve your issue download AnyDesk and share the 9-digit code. Call +91 98111 22334"}),
                (8, "tx", {"amount": 19_999, "to": ("PhonePe Support Desk", "phonepe.support.help@ybl")}),
                (10, "tx", {"amount": 19_999, "to": ("PhonePe Support Desk", "phonepe.support.help@ybl")}),
            ]},
        "investment": {
            "title": "Investment / task scam",
            "summary": "A trading group pays a small 'profit' first, then asks for growing deposits.",
            "steps": [
                (0, "message", {"text": "Join our VIP trading group. Guaranteed 30% return every week, daily income from home. Limited seats, act now!"}),
                (60, "rx", {"amount": 1_000, "from": ("AlphaGains Desk", "alphagains.desk@ibl"),
                            "answers": {"knows_sender": "unsure", "in_bank": "yes", "asked_to_pay": "yes"}}),
                (180, "tx", {"amount": 10_000, "to": ("AlphaGains Desk", "alphagains.desk@ibl")}),
                (420, "tx", {"amount": 25_000, "to": ("AlphaGains Desk", "alphagains.desk@ibl")}),
                (900, "tx", {"amount": 50_000, "to": ("AlphaGains Desk", "alphagains.desk@ibl")}),
            ]},
        "qr_scam": {
            "title": "QR scam",
            "summary": "A QR sticker promises cashback, but scanning a QR always sends money.",
            "steps": [
                (0, "qr", {"payload": "upi://pay?pa=cashback.reward.kyc@ybl&pn=Cashback%20Reward&am=2000&cu=INR&tn=Scan%20to%20receive%20cashback"}),
                (1, "tx", {"amount": 2_000, "to": ("Cashback Reward", "cashback.reward.kyc@ybl")}),
            ]},
        "phishing": {
            "title": "Phishing link",
            "summary": "A 'cashback' link imitates a payment app and asks for an OTP.",
            "steps": [
                (0, "message", {"text": "Congratulations! You have won Rs 5,000 Paytm cashback. Claim now: http://paytm-cashback.example/claim?otp= before midnight"}),
                (2, "url", {"url": "http://paytm-cashback.example/claim?otp=&user=you"}),
                (6, "tx", {"amount": 1, "to": ("Paytm Cashback", "paytm.cashback.claim@ybl")}),
            ]},
        "screenshot_fraud": {
            "title": "Fake payment screenshot",
            "summary": "A buyer sends a 'payment received' screenshot, but no money reaches the bank.",
            "steps": [
                (0, "message", {"text": "Sir payment done ✅ 15,000 sent, see screenshot. Please hand over the phone to my driver, he is waiting outside, urgent."}),
                (2, "rx", {"amount": 15_000, "from": ("Buyer (OLX)", "buyer.deal22@ybl"),
                           "answers": {"knows_sender": "no", "in_bank": "no", "asked_to_pay": "no"}}),
            ]},
    }


SCENARIOS = _scenarios()


def list_scenarios() -> list[dict]:
    return [{"id": k, "title": v["title"], "summary": v["summary"], "steps": len(v["steps"])} for k, v in SCENARIOS.items()]


def run(scenario_id: str, start: datetime | None = None) -> dict:
    sc = SCENARIOS[scenario_id]
    start = (start or datetime.now()).replace(second=0, microsecond=0)
    if scenario_id == "account_takeover":
        start = start.replace(hour=0, minute=41)
    # stable per-scenario seed (str hash() is randomised per process)
    history, balance = baseline_history(start, seed=sum(map(ord, scenario_id)))
    baseline_count = len(history)
    next_id = count(baseline_count + 1)
    events, detected = [], {}

    for minutes, kind, spec in sc["steps"]:
        at = start + timedelta(minutes=minutes)
        ev = {"at": at.isoformat(timespec="minutes"), "kind": kind}
        if kind == "event":
            ev.update(title=spec["title"], detail=spec["detail"], level=None)
            if spec.get("device"):
                detected.setdefault("NEW_DEVICE_LOGIN", "Login from a new device")
        elif kind == "message":
            r = M.analyze(spec["text"])
            ev.update(title="Message received", detail=spec["text"], level=r["level"],
                      signals=[i["text"] for i in r["indicators"]], analysis={"likely_scam": r["likely_scam"]})
            for i in r["indicators"]:
                detected.setdefault(i["code"], i["category"])
        elif kind == "url":
            r = URL.analyze(spec["url"])
            ev.update(title="Link opened", detail=spec["url"], level={"HIGH RISK": "high", "SUSPICIOUS": "medium"}.get(r["verdict"], "low"),
                      signals=[s["text"] for s in r["signals"] if s["kind"] == "warning"], analysis={"verdict": r["verdict"]})
            for s in r["signals"]:
                if s["kind"] == "warning" and s["weight"] >= 0.25:
                    detected.setdefault(s["code"], s["text"].split(".")[0])
        elif kind == "qr":
            r = Q.analyze(spec["payload"])
            ev.update(title="QR scanned", detail=spec["payload"], level=r["level"],
                      signals=[w["text"] for w in r["warnings"]], analysis={"payment": r["payment"]})
            for w in r["warnings"]:
                if w["weight"] >= 0.25:
                    detected.setdefault(w["code"], w["text"].split(".")[0])
        else:  # tx / rx
            if kind == "tx":
                name, vpa = spec["to"]
                amount = balance if spec["amount"] == "rest" else float(spec["amount"])
                tx = SimTx(next(next_id), at, "cash_out" if spec.get("cash_out") else "sent", amount, name, vpa,
                           balance, max(balance - amount, 0.0), device_id=spec.get("device", HOME_DEVICE))
                balance = tx.balance_after
            else:
                name, vpa = spec["from"]
                tx = SimTx(next(next_id), at, "received", float(spec["amount"]), name, vpa,
                           received_answers=spec.get("answers"))
                if (spec.get("answers") or {}).get("in_bank") != "no":
                    balance += tx.amount
            r = assess(tx, history)
            history.append(tx)
            arrow = "←" if tx.direction == "received" else "→"
            ev.update(title=f"₹{tx.amount:,.0f} {arrow} {vpa}", detail=f"{tx.direction.replace('_', ' ')} · balance after ₹{balance:,.0f}",
                      level=r["level"], score=r["points"], signals=[x["text"] for x in r["reasons"]],
                      breakdown=r["breakdown"], transaction=_tx_dict(tx))
            for p in r["components"]["patterns"]["items"]:
                detected.setdefault(p["code"], p["title"])
            if r["components"]["model"].get("available") and r["components"]["model"]["level"] != "low":
                detected.setdefault("MODEL", f"ML model: {r['components']['model']['level']} risk")
            if r["components"]["rules"].get("available") and r["components"]["rules"]["level"] != "low":
                detected.setdefault("RULES", f"Received-money rules: {r['components']['rules']['level']} risk")
        events.append(ev)

    levels = [e["level"] for e in events if e.get("level")]
    final = max(levels, key=lambda l: ["low", "medium", "high"].index(l), default="low")
    return {"scenario": scenario_id, "title": sc["title"], "summary": sc["summary"], "label": SYNTHETIC_LABEL,
            "baseline": {"transactions": baseline_count, "days": 45},
            "events": events, "detected": [{"code": k, "label": v} for k, v in detected.items()],
            "final_level": final}


def _tx_dict(t: SimTx) -> dict:
    return {"occurred_at": t.occurred_at.isoformat(timespec="minutes"), "direction": t.direction, "amount": t.amount,
            "counterparty_name": t.counterparty_name, "counterparty_upi": t.counterparty_upi,
            "balance_before": t.balance_before, "balance_after": t.balance_after, "device_id": t.device_id,
            "received_answers": t.received_answers}


# ---------- demo dataset for a user's history ----------

# Synthetic third-party money flows between demo UPI IDs (only shown in the network graph, labelled synthetic):
# a mule ring that forwards the account-takeover money and loops back.
DEMO_NETWORK = [
    ("quickpay.mule01@axl", "swiftwallet.cash@ibl", 45_000),
    ("swiftwallet.cash@ibl", "cryptoex.otc@ybl", 38_000),
    ("cryptoex.otc@ybl", "quickpay.mule01@axl", 12_000),
    ("alphagains.desk@ibl", "swiftwallet.cash@ibl", 30_000),
    ("refund.desk24@ybl", "swiftwallet.cash@ibl", 4_500),
    ("kyc.verify.cell@ybl", "cryptoex.otc@ybl", 20_000),
]


def demo_dataset(end: datetime) -> list[SimTx]:
    """~90 days of normal activity with a few scam episodes embedded, for a user's history."""
    txs, balance = baseline_history(end - timedelta(days=4), days=90, seed=42, start_balance=140_000)
    next_id = count(len(txs) + 1)

    def add(at, direction, amount, name, vpa, device=HOME_DEVICE, answers=None):
        nonlocal balance
        t = SimTx(next(next_id), at, direction, float(amount), name, vpa, device_id=device, received_answers=answers)
        if direction == "received":
            balance += amount
        else:
            t.balance_before, t.balance_after = balance, max(balance - amount, 0.0)
            balance = t.balance_after
        txs.append(t)

    day = (end - timedelta(days=3)).replace(second=0, microsecond=0)
    # investment scam over a day
    add(day.replace(hour=11, minute=5), "received", 1_000, "AlphaGains Desk", "alphagains.desk@ibl",
        answers={"knows_sender": "unsure", "in_bank": "yes", "asked_to_pay": "yes"})
    add(day.replace(hour=14, minute=10), "sent", 10_000, "AlphaGains Desk", "alphagains.desk@ibl")
    add(day.replace(hour=18, minute=40), "sent", 15_000, "AlphaGains Desk", "alphagains.desk@ibl")
    # fake refund QR
    d2 = day + timedelta(days=1)
    add(d2.replace(hour=16, minute=22), "sent", 4_999, "Refund Desk", "refund.desk24@ybl")
    # account takeover at night from a new device
    d3 = day + timedelta(days=2)
    for minute, amount, name, vpa in [(48, 50_000, "Rahul Traders", "quickpay.mule01@axl"),
                                      (49, 40_000, "Rahul Traders", "quickpay.mule01@axl"),
                                      (51, 20_000, "Swift Wallet Svc", "swiftwallet.cash@ibl")]:
        add(d3.replace(hour=0, minute=minute), "sent", amount, name, vpa, device="iphone-x91")
    # a normal day after
    add(d3.replace(hour=13, minute=15), "sent", 240, "Chai Point", "chaipoint.ka@ybl")
    txs.sort(key=lambda t: t.occurred_at)
    return txs


def stream_transaction(user_history: list, rng: random.Random, now: datetime) -> SimTx:
    """One synthetic live transaction for demo mode: mostly normal, sometimes suspicious."""
    last_balance = next((t.balance_after for t in reversed(user_history) if t.balance_after is not None), 60_000.0)
    roll = rng.random()
    if roll < 0.75:
        name, vpa, cat, (lo, hi) = rng.choice(NORMAL_PAYEES)
        amount, device = float(round(rng.uniform(lo, hi), -1) or lo), HOME_DEVICE
    elif roll < 0.9:
        name, vpa, amount, device = "Quick Loan Desk", f"instaloan.{rng.randint(10, 99)}@ybl", float(rng.choice([9_999, 14_999, 24_999])), HOME_DEVICE
    else:
        name, vpa, amount, device = "Rahul Traders", "quickpay.mule01@axl", float(min(last_balance * 0.95, 45_000)), "iphone-x91"
    amount = max(1.0, min(amount, last_balance)) if last_balance > 1 else amount
    return SimTx(0, now, "sent", amount, name, vpa, last_balance, max(last_balance - amount, 0.0), device_id=device)


__all__ = ["SYNTHETIC_LABEL", "SCENARIOS", "list_scenarios", "run", "demo_dataset", "DEMO_NETWORK",
           "stream_transaction", "level_of"]

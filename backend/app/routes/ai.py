"""AI Investigator: answers questions about the user's own transaction evidence with an LLM.

The provider (Anthropic, OpenAI, Azure OpenAI or Gemini) is chosen by configuration; see app/llm.py.

Safety design (identical for every provider):
- Opt-in: the user must enable AI in Settings (data is sent to the AI provider) and confirm per request.
- The model reads data only through the tools below, each scoped to the signed-in user. It never sees
  the database directly and never sees other users' data.
- It must cite every fact as [tx#ID] / [case#ID]; the server checks each citation against the
  records the tools actually returned and flags anything it can't match.
- It explains evidence produced by the model, rules and patterns; it does not invent fraud reasons.
- Per-user daily limit (AI_DAILY_LIMIT) for cost control.
"""

import json
import re
import time
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, llm, services as S
from ..auth import audit, current_user
from ..db import get_db
from ..engine import patterns as P, upi as U
from ..models import AuditLog, Case, Note, Transaction, User

router = APIRouter(prefix="/api/ai", tags=["ai investigator"])

DEADLINE_SECONDS = 50  # stay inside the serverless function limit (vercel.json maxDuration)

SYSTEM = """You are UPI Guard's fraud investigator. You help one user understand their own UPI transactions.

Rules:
- Use only facts returned by your tools. Never guess amounts, dates, names, UPI IDs or risk levels. If the tools don't return something, say you don't have that information.
- Cite every factual statement about a transaction or case inline as [tx#ID] or [case#ID], using the IDs from tool results.
- Explain the evidence the system already produced (ML model reasons, received-money rules, history patterns, community reports). Do not invent new fraud reasons. You may say how the evidence fits a known scam type (e.g. account takeover), framed as "consistent with", not as a conclusion.
- Never say a person is a criminal or that a transaction is definitely fraud unless the user has marked it as confirmed fraud. Say "potentially suspicious" or "high-risk pattern".
- Risk scores are estimates. Community reports are unverified.
- Never ask for or repeat a UPI PIN, OTP, password or card number.
- If money may have been lost, mention calling 1930 and cybercrime.gov.in.
- Be concise: a short answer first, then an "Evidence:" list with one cited line per fact. Amounts in rupees (₹)."""

NULLABLE_STR = {"type": ["string", "null"]}
TOOLS = [
    {"name": "get_transaction", "strict": True,
     "description": "One of the user's transactions with its full risk assessment: unified score and level, per-component breakdown, ML model reasons (SHAP), received-money rule reasons, detected history patterns, the user's baseline, and review status.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["transaction_id"],
                      "properties": {"transaction_id": {"type": "integer"}}}},
    {"name": "search_transactions", "strict": True,
     "description": "Search the user's transactions. Use null for filters you don't need. Dates are YYYY-MM-DD. Returns at most `limit` rows (max 50) with id, time, direction, amount, counterparty, risk level and score, and which patterns fired.",
     "input_schema": {"type": "object", "additionalProperties": False,
                      "required": ["min_amount", "max_amount", "direction", "risk_level", "counterparty", "pattern",
                                   "date_from", "date_to", "sort", "limit"],
                      "properties": {
                          "min_amount": {"type": ["number", "null"]}, "max_amount": {"type": ["number", "null"]},
                          "direction": {"type": ["string", "null"], "description": "sent, received or cash_out"},
                          "risk_level": {"type": ["string", "null"], "description": "low, medium or high"},
                          "counterparty": NULLABLE_STR,
                          "pattern": {"type": ["string", "null"], "description": "pattern code, e.g. NEW_RECIPIENT, RAPID_TRANSFER, UNUSUAL_AMOUNT"},
                          "date_from": NULLABLE_STR, "date_to": NULLABLE_STR,
                          "sort": {"type": "string", "enum": ["newest", "oldest", "risk", "amount"]},
                          "limit": {"type": "integer"}}}},
    {"name": "get_related", "strict": True,
     "description": "Transactions related to one transaction: same counterparty, within the same hour, and a 24-hour timeline around it.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["transaction_id"],
                      "properties": {"transaction_id": {"type": "integer"}}}},
    {"name": "get_case", "strict": True,
     "description": "One of the user's fraud cases: status, priority, linked transactions, evidence items and notes.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["case_id"],
                      "properties": {"case_id": {"type": "integer"}}}},
    {"name": "get_profile", "strict": True,
     "description": "The user's normal behaviour: number of transactions, median and typical payment range, common hours, top counterparties, and counts by risk level.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": [], "properties": {}}},
    {"name": "check_upi", "strict": True,
     "description": "Facts about a UPI ID: format validity, payment app/bank from the handle, warning signs in the name, unverified community report count, and the user's own history with it.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["vpa"],
                      "properties": {"vpa": {"type": "string"}}}},
]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    consent: bool
    transaction_id: Optional[int] = None
    case_id: Optional[int] = None
    history: list[Turn] = Field(default_factory=list, max_length=6)


# ---------- tools (all scoped to `user`) ----------

def _tx_brief(t: Transaction) -> dict:
    pats = [p["code"] for p in (((t.risk or {}).get("components") or {}).get("patterns") or {}).get("items", [])]
    return {"id": t.id, "occurred_at": t.occurred_at.isoformat(timespec="minutes"), "direction": t.direction,
            "amount": t.amount, "counterparty_name": t.counterparty_name, "counterparty_upi": t.counterparty_upi,
            "payment_app": t.payment_app, "status": t.status, "risk_level": t.risk_level,
            "risk_score": round((t.risk_score or 0) * 100), "patterns": pats, "review_status": t.review_status,
            "synthetic": t.is_synthetic}


class Tools:
    def __init__(self, db: Session, user: User):
        self.db, self.user = db, user
        self.seen_tx: set[int] = set()
        self.seen_case: set[int] = set()

    def _own_tx(self, tx_id: int) -> Transaction | None:
        t = self.db.get(Transaction, int(tx_id))
        return t if t and t.user_id == self.user.id else None

    def _see(self, txs):
        self.seen_tx |= {t.id for t in txs}

    def get_transaction(self, transaction_id):
        t = self._own_tx(transaction_id)
        if not t:
            return {"error": f"No transaction #{transaction_id} in this user's history."}
        model = ((t.risk or {}).get("components") or {}).get("model") or {}
        if not t.risk or (model.get("available") and not model.get("explained")):
            S.score(self.db, t, S.history(self.db, self.user), explain=True)
            self.db.commit()
        self._see([t])
        r = t.risk or {}
        comps = r.get("components", {})
        return {**_tx_brief(t), "balance_before": t.balance_before, "balance_after": t.balance_after,
                "device_id": t.device_id, "received_answers": t.received_answers,
                "risk": {"score": r.get("points"), "level": r.get("level"), "breakdown": r.get("breakdown"),
                         "model": {k: comps.get("model", {}).get(k) for k in ("available", "probability", "level", "reasons", "note")},
                         "rules": {k: comps.get("rules", {}).get(k) for k in ("available", "level", "reasons", "note")},
                         "patterns": comps.get("patterns", {}).get("items", []),
                         "community_reports": comps.get("reputation", {}).get("reports", 0),
                         "baseline": r.get("baseline"), "notes": r.get("notes")}}

    def search_transactions(self, min_amount=None, max_amount=None, direction=None, risk_level=None,
                            counterparty=None, pattern=None, date_from=None, date_to=None, sort="newest", limit=20):
        if direction not in (None, "sent", "received", "cash_out"):
            return {"error": "direction must be sent, received, cash_out or null."}
        if risk_level not in (None, "low", "medium", "high"):
            return {"error": "risk_level must be low, medium, high or null."}
        cond = [Transaction.user_id == self.user.id]
        if min_amount is not None:
            cond.append(Transaction.amount >= float(min_amount))
        if max_amount is not None:
            cond.append(Transaction.amount <= float(max_amount))
        if direction:
            cond.append(Transaction.direction == direction)
        if risk_level:
            cond.append(Transaction.risk_level == risk_level)
        if counterparty:
            like = f"%{str(counterparty).lower()[:80]}%"
            cond.append(func.lower(func.coalesce(Transaction.counterparty_upi, "") + " " +
                                   func.coalesce(Transaction.counterparty_name, "")).like(like))
        for value, op in ((date_from, ">="), (date_to, "<=")):
            if value:
                try:
                    d = datetime.fromisoformat(str(value)[:10])
                except ValueError:
                    return {"error": f"Bad date '{value}', use YYYY-MM-DD."}
                cond.append(Transaction.occurred_at >= d if op == ">=" else Transaction.occurred_at < d + timedelta(days=1))
        order = {"newest": Transaction.occurred_at.desc(), "oldest": Transaction.occurred_at,
                 "risk": Transaction.risk_score.desc(), "amount": Transaction.amount.desc()}.get(sort, Transaction.occurred_at.desc())
        rows = self.db.scalars(select(Transaction).where(*cond).order_by(order).limit(500)).all()
        if pattern:
            rows = [t for t in rows if pattern in _tx_brief(t)["patterns"]]
        rows = rows[:max(1, min(int(limit or 20), 50))]
        self._see(rows)
        return {"count": len(rows), "transactions": [_tx_brief(t) for t in rows]}

    def get_related(self, transaction_id):
        t = self._own_tx(transaction_id)
        if not t:
            return {"error": f"No transaction #{transaction_id} in this user's history."}
        txs = S.history(self.db, self.user)
        rel = S.related(self.db, self.user, t, txs)
        tl = S.timeline(t, txs)
        self._see([t, *rel["same_counterparty"], *rel["same_hour"], *tl])
        return {"transaction_id": t.id,
                "same_counterparty": [_tx_brief(x) for x in rel["same_counterparty"][-20:]],
                "same_hour": [_tx_brief(x) for x in rel["same_hour"][-20:]],
                "timeline_24h": [_tx_brief(x) for x in tl[-40:]]}

    def get_case(self, case_id):
        c = self.db.get(Case, int(case_id))
        if not c or c.user_id != self.user.id:
            return {"error": f"No case #{case_id} for this user."}
        self.seen_case.add(c.id)
        self._see(c.transactions)
        notes = self.db.scalars(select(Note).where(Note.case_id == c.id).order_by(Note.created_at)).all()
        return {"id": c.id, "title": c.title, "status": c.status, "priority": c.priority, "resolution": c.resolution,
                "transactions": [_tx_brief(t) for t in sorted(c.transactions, key=lambda t: t.occurred_at)],
                "evidence": [{"type": e["type"], "label": e["label"], "added_at": e["added_at"]} for e in (c.evidence or [])],
                "notes": [{"at": n.created_at.isoformat(timespec="minutes"), "text": n.text} for n in notes]}

    def get_profile(self):
        txs = S.history(self.db, self.user)
        base = P.baseline(txs)
        tops = {}
        for t in txs:
            k = P.party(t)
            if k:
                tops[k] = tops.get(k, 0) + 1
        return {**base, "risk_counts": {lvl: sum(t.risk_level == lvl for t in txs) for lvl in ("low", "medium", "high")},
                "top_counterparties": sorted(tops.items(), key=lambda kv: -kv[1])[:8],
                "synthetic_transactions": sum(t.is_synthetic for t in txs)}

    def check_upi(self, vpa):
        info = U.inspect(str(vpa)[:300])
        txs = self.db.scalars(select(Transaction).where(Transaction.user_id == self.user.id,
                                                        Transaction.counterparty_upi == info["vpa"])).all()
        self._see(txs)
        return {**info, "community_reports_unverified": S.reporter_count(self.db, info["vpa"]),
                "your_transactions": [_tx_brief(t) for t in txs[-20:]]}

    def run(self, name: str, args: dict) -> dict:
        fn = getattr(self, name, None) if name in {t["name"] for t in TOOLS} else None
        if fn is None:
            return {"error": f"Unknown tool {name}"}
        try:
            return fn(**(args or {}))
        except (TypeError, ValueError) as e:
            return {"error": f"Bad arguments: {e}"}


CITE_RE = re.compile(r"\[(tx|case)#(\d+)\]")


def check_citations(text: str, tools: Tools) -> tuple[str, list[dict], list[str]]:
    """Keep citations that point at records the tools returned; flag the rest."""
    cited, unverified = [], []
    for kind, num in CITE_RE.findall(text):
        n = int(num)
        ok = n in (tools.seen_tx if kind == "tx" else tools.seen_case)
        (cited if ok else unverified).append({"type": kind, "id": n} if ok else f"{kind}#{n}")
    text = CITE_RE.sub(lambda m: m.group(0) if int(m.group(2)) in (tools.seen_tx if m.group(1) == "tx" else tools.seen_case)
                       else f"[{m.group(1)}#{m.group(2)} – not found in your data]", text)
    uniq = list({(c["type"], c["id"]): c for c in cited}.values())
    return text, uniq, sorted(set(unverified))


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = llm.status()
    return {"configured": s["configured"], "provider": s["provider"], "provider_label": s.get("provider_label"),
            "model": s["model"], "reason": s["reason"], "consent": bool((user.settings or {}).get("ai_consent")),
            "daily_limit": config.AI_DAILY_LIMIT, "used_today": _used_today(db, user)}


def _used_today(db: Session, user: User) -> int:
    since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.user_id == user.id, AuditLog.action == "ai.ask", AuditLog.created_at >= since)) or 0


@router.post("/ask")
def ask(body: AskBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.consent or not (user.settings or {}).get("ai_consent"):
        raise HTTPException(status_code=403, detail="Turn on the AI investigator in Settings first. Your question and "
                                                    "the transaction data it needs are sent to the AI provider's API.")
    provider = llm.get_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail="The AI investigator isn't configured on this server. "
                                                    + (llm.status()["reason"] or ""))
    if _used_today(db, user) >= config.AI_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail=f"Daily limit of {config.AI_DAILY_LIMIT} AI questions reached.")

    tools = Tools(db, user)
    focus = []
    if body.transaction_id is not None:
        focus.append(f"The user is looking at transaction #{body.transaction_id}.")
    if body.case_id is not None:
        focus.append(f"The user is looking at case #{body.case_id}.")
    messages = [{"role": t.role, "content": t.text} for t in body.history]
    if messages and messages[0]["role"] != "user":
        messages = messages[1:]
    messages.append({"role": "user", "content": (" ".join(focus) + "\n\n" if focus else "") + body.question})

    audit(db, user.id, "ai.ask", transaction_id=body.transaction_id, case_id=body.case_id)
    db.commit()

    try:
        ans = provider.run(SYSTEM, TOOLS, messages, tools.run, deadline=time.monotonic() + DEADLINE_SECONDS)
    except llm.LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)

    base = {"tool_calls": ans.calls, "model": ans.model, "provider": provider.name}
    if ans.refused:
        return {"answer": "The AI declined to answer this question.", "evidence": [], "unverified": [], **base}
    text = ans.text
    if ans.stopped_early:
        text = (text + "\n\n" if text else "") + "(Stopped after too many lookups. Try a more specific question.)"
    text, cited, unverified = check_citations(text, tools)
    return {"answer": text or "No answer.", "evidence": cited, "unverified": unverified, **base}

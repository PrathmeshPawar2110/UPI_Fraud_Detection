"""AI investigator with a fake Claude client (no network, no API key needed)."""

from types import SimpleNamespace as NS

import pytest

from app import config
from app.routes import ai

NOW = "2026-09-20T03:00:00"


class FakeMessages:
    """Scripted responses: each item is a list of content blocks; tool calls are executed by the route."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kw):
        self.calls.append(kw)
        blocks = self.script.pop(0)(kw) if callable(self.script[0]) else self.script.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return NS(content=blocks, stop_reason=stop, model=kw["model"])


def fake_client(script):
    msgs = FakeMessages(script)
    return NS(beta=NS(messages=msgs)), msgs


def text(t):
    return NS(type="text", text=t)


def tool(name, **inp):
    return NS(type="tool_use", id=f"tu_{name}", name=name, input=inp)


@pytest.fixture
def ai_user(user, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    user.patch("/api/account/settings", json={"ai_consent": True})
    tid = user.post("/api/transactions", json={"occurred_at": NOW, "direction": "sent", "amount": 181000,
                                               "counterparty_upi": "mule@axl", "balance_before": 181000}).json()["id"]
    return user, tid


def test_requires_consent(user, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    r = user.post("/api/ai/ask", json={"question": "why?", "consent": True})
    assert r.status_code == 403 and "Settings" in r.json()["detail"]
    user.patch("/api/account/settings", json={"ai_consent": True})
    assert user.post("/api/ai/ask", json={"question": "why?", "consent": False}).status_code == 403


def test_not_configured(user, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    user.patch("/api/account/settings", json={"ai_consent": True})
    assert user.post("/api/ai/ask", json={"question": "why?", "consent": True}).status_code == 503


def test_tool_loop_answers_with_verified_citations(ai_user, monkeypatch):
    user, tid = ai_user
    client, msgs = fake_client([
        [tool("get_transaction", transaction_id=tid)],
        lambda kw: [text(f"It was flagged high risk [tx#{tid}]. Also see [tx#99999].\n\nEvidence:\n- ₹1,81,000 sent [tx#{tid}]")],
    ])
    monkeypatch.setattr(ai, "get_client", lambda: client)
    r = user.post("/api/ai/ask", json={"question": "Why was this flagged?", "consent": True, "transaction_id": tid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evidence"] == [{"type": "tx", "id": tid}]
    assert body["unverified"] == ["tx#99999"] and "not found in your data" in body["answer"]
    assert body["tool_calls"][0]["tool"] == "get_transaction"
    # the tool result fed back to Claude contains the real stored evidence
    second = msgs.calls[1]["messages"]
    result = second[-1]["content"][0]
    assert result["type"] == "tool_result" and '"level": "high"' in result["content"]
    # request shape: strict tools, cached system prompt, focus context, refusal fallback
    first = msgs.calls[0]
    assert all(t["strict"] for t in first["tools"])
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert f"transaction #{tid}" in first["messages"][0]["content"]  # (fake keeps a live reference to the list)
    assert first["fallbacks"] == "default"


def test_tools_cannot_read_other_users_data(ai_user, other_user, monkeypatch):
    user, tid = ai_user
    other_user.patch("/api/account/settings", json={"ai_consent": True})
    client, msgs = fake_client([[tool("get_transaction", transaction_id=tid)], [text("I couldn't find it.")]])
    monkeypatch.setattr(ai, "get_client", lambda: client)
    r = other_user.post("/api/ai/ask", json={"question": f"Tell me about #{tid}", "consent": True})
    result = msgs.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "No transaction" in result["content"]
    assert "181000" not in result["content"]
    assert r.json()["evidence"] == []


def test_search_tool_and_unknown_tool(ai_user, monkeypatch):
    user, tid = ai_user
    client, msgs = fake_client([
        [tool("search_transactions", min_amount=50000, max_amount=None, direction=None, risk_level="high",
              counterparty=None, pattern=None, date_from=None, date_to=None, sort="amount", limit=5),
         tool("drop_tables")],
        [text(f"One high-risk payment [tx#{tid}].")],
    ])
    monkeypatch.setattr(ai, "get_client", lambda: client)
    r = user.post("/api/ai/ask", json={"question": "Highest risk payments above 50k?", "consent": True}).json()
    results = msgs.calls[1]["messages"][-1]["content"]
    assert '"count": 1' in results[0]["content"]
    assert results[1]["is_error"] is True
    assert r["evidence"] == [{"type": "tx", "id": tid}]


def test_daily_limit(ai_user, monkeypatch):
    user, _ = ai_user
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 2)
    monkeypatch.setattr(ai, "get_client", lambda: fake_client([[text("ok")]])[0])
    for _ in range(2):
        assert user.post("/api/ai/ask", json={"question": "hi there", "consent": True}).status_code == 200
    assert user.post("/api/ai/ask", json={"question": "hi there", "consent": True}).status_code == 429


def test_status(ai_user):
    user, _ = ai_user
    s = user.get("/api/ai/status").json()
    assert s["configured"] and s["consent"] and s["model"] == config.AI_MODEL

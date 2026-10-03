"""AI investigator with fake LLM clients (no network, no API keys needed).

Anthropic uses the Messages API shape; OpenAI, Azure OpenAI and Gemini share the Chat Completions shape.
"""

import json
from types import SimpleNamespace as NS

import pytest

from app import config, llm

NOW = "2026-09-20T03:00:00"


# ---------- fake Anthropic client ----------

class FakeAnthropic:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.beta = NS(messages=self)

    def create(self, **kw):
        self.calls.append(kw)
        blocks = self.script.pop(0)
        blocks = blocks(kw) if callable(blocks) else blocks
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return NS(content=blocks, stop_reason=stop, model=kw["model"])


def text(t):
    return NS(type="text", text=t)


def tool(name, **inp):
    return NS(type="tool_use", id=f"tu_{name}", name=name, input=inp)


# ---------- fake OpenAI-compatible client ----------

class FakeChat:
    """Each script item is a list of (name, args) tool calls, or a final text string."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.chat = NS(completions=self)

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        step = self.script.pop(0)
        if isinstance(step, str):
            msg = NS(content=step, tool_calls=None, refusal=None)
            return NS(choices=[NS(message=msg, finish_reason="stop")], model=kw["model"])
        calls = [NS(id=f"call_{i}", type="function",
                    function=NS(name=name, arguments=args if isinstance(args, str) else json.dumps(args)))
                 for i, (name, args) in enumerate(step)]
        msg = NS(content=None, tool_calls=calls, refusal=None)
        return NS(choices=[NS(message=msg, finish_reason="tool_calls")], model=kw["model"])


def use(monkeypatch, provider):
    monkeypatch.setattr(llm, "get_provider", lambda: provider)


@pytest.fixture
def ai_user(user, monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    user.patch("/api/account/settings", json={"ai_consent": True})
    tid = user.post("/api/transactions", json={"occurred_at": NOW, "direction": "sent", "amount": 181000,
                                               "counterparty_upi": "mule@axl", "balance_before": 181000}).json()["id"]
    return user, tid


# ---------- consent & configuration ----------

def test_requires_consent(user, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")
    r = user.post("/api/ai/ask", json={"question": "why?", "consent": True})
    assert r.status_code == 403 and "Settings" in r.json()["detail"]
    user.patch("/api/account/settings", json={"ai_consent": True})
    assert user.post("/api/ai/ask", json={"question": "why?", "consent": False}).status_code == 403


def test_not_configured(user, monkeypatch):
    for k in ("AI_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY"):
        monkeypatch.setattr(config, k, "")
    user.patch("/api/account/settings", json={"ai_consent": True})
    r = user.post("/api/ai/ask", json={"question": "why?", "consent": True})
    assert r.status_code == 503 and "No AI provider key" in r.json()["detail"]


@pytest.mark.parametrize("env,expect", [
    ({"ANTHROPIC_API_KEY": "k"}, ("anthropic", True, "claude-opus-5-5")),
    ({"OPENAI_API_KEY": "k", "AI_MODEL": "gpt-x"}, ("openai", True, "gpt-x")),
    ({"OPENAI_API_KEY": "k"}, ("openai", False, None)),                              # model required
    ({"GEMINI_API_KEY": "k", "AI_MODEL": "gemini-x"}, ("gemini", True, "gemini-x")),
    ({"AZURE_OPENAI_API_KEY": "k", "AZURE_OPENAI_DEPLOYMENT": "dep"}, ("azure", False, "dep")),  # endpoint required
    ({"AZURE_OPENAI_API_KEY": "k", "AZURE_OPENAI_DEPLOYMENT": "dep",
      "AZURE_OPENAI_ENDPOINT": "https://r.openai.azure.com"}, ("azure", True, "dep")),
    ({"AI_PROVIDER": "gemini", "OPENAI_API_KEY": "k", "AI_MODEL": "m"}, ("gemini", False, None)),  # chosen but no key
    ({"AI_PROVIDER": "mistral", "OPENAI_API_KEY": "k"}, ("mistral", False, None)),
    ({"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o", "AI_MODEL": "gpt-x", "AI_PROVIDER": "openai"}, ("openai", True, "gpt-x")),
])
def test_provider_selection(monkeypatch, env, expect):
    for k in ("AI_PROVIDER", "AI_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY",
              "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"):
        v = env.get(k, "")
        monkeypatch.setattr(config, k, "sk-SECRET-123" if v == "k" else v)
    s = llm.status()
    assert (s["provider"], s["configured"], s["model"]) == expect, s
    assert s["configured"] or s["reason"]
    assert "SECRET" not in json.dumps(s)  # never echoes secrets


def test_gemini_schema_has_no_type_unions():
    from app.routes.ai import TOOLS
    p = llm.OpenAICompatProvider("gemini", "m")
    search = next(t for t in p._tools(TOOLS) if t["function"]["name"] == "search_transactions")["function"]
    assert "additionalProperties" not in json.dumps(search)

    def type_unions(node):
        if isinstance(node, dict):
            return (isinstance(node.get("type"), list)) + sum(type_unions(v) for v in node.values())
        return sum(type_unions(v) for v in node) if isinstance(node, list) else 0
    assert type_unions(search) == 0
    assert search["parameters"]["properties"]["min_amount"] == {"type": "number", "nullable": True}
    openai_tools = llm.OpenAICompatProvider("openai", "m")._tools(TOOLS)
    assert all(t["function"]["strict"] for t in openai_tools)


# ---------- Anthropic tool loop ----------

def test_anthropic_loop_answers_with_verified_citations(ai_user, monkeypatch):
    user, tid = ai_user
    fake = FakeAnthropic([
        [tool("get_transaction", transaction_id=tid)],
        lambda kw: [text(f"It was flagged high risk [tx#{tid}]. Also see [tx#99999].\n\nEvidence:\n- ₹1,81,000 sent [tx#{tid}]")],
    ])
    use(monkeypatch, llm.AnthropicProvider("claude-opus-5-5", client=fake))
    r = user.post("/api/ai/ask", json={"question": "Why was this flagged?", "consent": True, "transaction_id": tid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "anthropic"
    assert body["evidence"] == [{"type": "tx", "id": tid}]
    assert body["unverified"] == ["tx#99999"] and "not found in your data" in body["answer"]
    assert body["tool_calls"][0]["tool"] == "get_transaction"
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and '"level": "high"' in result["content"]
    first = fake.calls[0]
    assert all(t["strict"] for t in first["tools"])
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert f"transaction #{tid}" in first["messages"][0]["content"]
    assert first["fallbacks"] == "default"


def test_tools_cannot_read_other_users_data(ai_user, other_user, monkeypatch):
    user, tid = ai_user
    other_user.patch("/api/account/settings", json={"ai_consent": True})
    fake = FakeAnthropic([[tool("get_transaction", transaction_id=tid)], [text("I couldn't find it.")]])
    use(monkeypatch, llm.AnthropicProvider("m", client=fake))
    r = other_user.post("/api/ai/ask", json={"question": f"Tell me about #{tid}", "consent": True})
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "No transaction" in result["content"]
    assert "181000" not in result["content"]
    assert r.json()["evidence"] == []


# ---------- OpenAI / Azure / Gemini tool loop ----------

@pytest.mark.parametrize("name", ["openai", "azure", "gemini"])
def test_openai_compatible_loop(ai_user, monkeypatch, name):
    user, tid = ai_user
    fake = FakeChat([
        [("search_transactions", {"min_amount": 50000, "max_amount": None, "direction": None, "risk_level": "high",
                                  "counterparty": None, "pattern": None, "date_from": None, "date_to": None,
                                  "sort": "amount", "limit": 5}),
         ("drop_tables", {}), ("get_transaction", "{not json")],
        f"One high-risk payment [tx#{tid}] and [tx#424242].",
    ])
    use(monkeypatch, llm.OpenAICompatProvider(name, "some-model", client=fake))
    body = user.post("/api/ai/ask", json={"question": "Highest risk payments above 50k?", "consent": True}).json()
    assert body["provider"] == name and body["model"] == "some-model"
    assert body["evidence"] == [{"type": "tx", "id": tid}] and body["unverified"] == ["tx#424242"]
    first, second = fake.calls
    assert first["messages"][0]["role"] == "system" and "fraud investigator" in first["messages"][0]["content"]
    assert ("max_tokens" if name == "gemini" else "max_completion_tokens") in first
    tool_msgs = [m for m in second["messages"] if m["role"] == "tool"]
    assert '"count": 1' in tool_msgs[0]["content"]
    assert "Unknown tool" in tool_msgs[1]["content"]
    assert "not valid JSON" in tool_msgs[2]["content"]
    assistant = next(m for m in second["messages"] if m["role"] == "assistant")
    assert [c["id"] for c in assistant["tool_calls"]] == [m["tool_call_id"] for m in tool_msgs]


def test_openai_errors_are_mapped(ai_user, monkeypatch):
    import openai
    user, _ = ai_user

    class Boom:
        chat = NS(completions=NS(create=lambda **kw: (_ for _ in ()).throw(openai.APIConnectionError(request=None))))

    use(monkeypatch, llm.OpenAICompatProvider("openai", "m", client=Boom()))
    r = user.post("/api/ai/ask", json={"question": "hello there", "consent": True})
    assert r.status_code == 502 and "Couldn't reach" in r.json()["detail"]


def test_daily_limit(ai_user, monkeypatch):
    user, _ = ai_user
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 2)
    monkeypatch.setattr(llm, "get_provider", lambda: llm.OpenAICompatProvider("openai", "m", client=FakeChat(["ok"])))
    for _ in range(2):
        assert user.post("/api/ai/ask", json={"question": "hi there", "consent": True}).status_code == 200
    assert user.post("/api/ai/ask", json={"question": "hi there", "consent": True}).status_code == 429


def test_status(ai_user):
    user, _ = ai_user
    s = user.get("/api/ai/status").json()
    assert s["configured"] and s["consent"] and s["provider"] == "anthropic" and s["model"] == "claude-opus-5-5"
    assert s["provider_label"] == "Anthropic Claude" and s["reason"] is None

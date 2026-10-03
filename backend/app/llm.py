"""LLM providers for the AI investigator: Anthropic, OpenAI, Azure OpenAI and Google Gemini.

Every provider runs the same tool loop over the same user-scoped tools (routes/ai.py), so the safety
properties (tools only see the user's own data, citations are checked afterwards) don't depend on
which model answers.

- anthropic : Anthropic SDK, Messages API with tools
- openai    : OpenAI SDK, Chat Completions with function tools
- azure     : OpenAI SDK's AzureOpenAI client (model = your deployment name)
- gemini    : OpenAI SDK against Google's OpenAI-compatible endpoint

Selection: AI_PROVIDER, or the first provider whose key is set (anthropic, openai, azure, gemini).
Only the Anthropic default model is built in; the others need AI_MODEL (or the Azure deployment)
because their model names change often.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from . import config

PROVIDERS = {
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI",
    "azure": "Azure OpenAI",
    "gemini": "Google Gemini",
}
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_TOOL_ROUNDS = 6
MAX_OUTPUT_TOKENS = 4000


class LLMError(Exception):
    """A provider error mapped to an HTTP status and a user-facing message."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class Answer:
    text: str
    model: str
    calls: list = field(default_factory=list)
    refused: bool = False
    stopped_early: bool = False


Executor = Callable[[str, dict], dict]


# ---------- configuration ----------

def _key_for(provider: str) -> str:
    return {"anthropic": config.ANTHROPIC_API_KEY, "openai": config.OPENAI_API_KEY,
            "azure": config.AZURE_OPENAI_API_KEY, "gemini": config.GEMINI_API_KEY}.get(provider, "")


def selected_provider() -> str | None:
    if config.AI_PROVIDER:
        return config.AI_PROVIDER
    return next((p for p in PROVIDERS if _key_for(p)), None)


def status() -> dict:
    """What's configured, and if not, why (shown in the UI, never includes secrets)."""
    p = selected_provider()
    if p is None:
        return {"configured": False, "provider": None, "model": None,
                "reason": "No AI provider key is set (ANTHROPIC_API_KEY, OPENAI_API_KEY, AZURE_OPENAI_API_KEY or GEMINI_API_KEY)."}
    if p not in PROVIDERS:
        return {"configured": False, "provider": p, "model": None,
                "reason": f"AI_PROVIDER '{p}' isn't supported. Use one of: {', '.join(PROVIDERS)}."}
    if not _key_for(p):
        return {"configured": False, "provider": p, "model": None, "reason": f"AI_PROVIDER is {p} but its API key isn't set."}
    model = _model_for(p)
    if not model:
        need = "AZURE_OPENAI_DEPLOYMENT (or AI_MODEL)" if p == "azure" else "AI_MODEL"
        return {"configured": False, "provider": p, "model": None, "reason": f"Set {need} for {PROVIDERS[p]}."}
    if p == "azure" and not config.AZURE_OPENAI_ENDPOINT:
        return {"configured": False, "provider": p, "model": model, "reason": "Set AZURE_OPENAI_ENDPOINT."}
    return {"configured": True, "provider": p, "provider_label": PROVIDERS[p], "model": model, "reason": None}


def _model_for(p: str) -> str:
    if p == "azure":
        return config.AZURE_OPENAI_DEPLOYMENT or config.AI_MODEL
    if p == "anthropic":
        return config.AI_MODEL or "claude-opus-5-5"
    return config.AI_MODEL


def get_provider():
    """The configured provider, or None. Separated so tests can replace it."""
    s = status()
    if not s["configured"]:
        return None
    if s["provider"] == "anthropic":
        return AnthropicProvider(s["model"])
    return OpenAICompatProvider(s["provider"], s["model"])


# ---------- Anthropic ----------

class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, client=None):
        self.model = model
        self._client = client

    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=40.0, max_retries=1)
        return self._client

    def run(self, system: str, tools: list[dict], messages: list[dict], execute: Executor, deadline: float) -> Answer:
        import anthropic

        msgs = list(messages)
        calls, response = [], None
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                if time.monotonic() > deadline:
                    break
                response = self.client().beta.messages.create(
                    model=self.model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    tools=[{**t, "strict": True} for t in tools],
                    messages=msgs,
                    output_config={"effort": "low"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
                if response.stop_reason != "tool_use":
                    break
                msgs.append({"role": "assistant", "content": response.content})  # append-only, blocks unchanged
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        out = execute(block.name, block.input)
                        calls.append({"tool": block.name, "input": block.input})
                        results.append({"type": "tool_result", "tool_use_id": block.id,
                                        "content": json.dumps(out, default=str)[:30_000],
                                        **({"is_error": True} if "error" in out else {})})
                msgs.append({"role": "user", "content": results})
        except anthropic.RateLimitError:
            raise LLMError(429, "The AI service is busy. Try again in a minute.")
        except anthropic.APITimeoutError:
            raise LLMError(504, "The AI investigator took too long. Try a narrower question.")
        except anthropic.APIConnectionError:
            raise LLMError(502, "Couldn't reach the AI service.")
        except anthropic.APIStatusError as e:
            raise LLMError(502, f"AI service error ({e.status_code}).")

        if response is None:
            raise LLMError(504, "The AI investigator took too long.")
        model = getattr(response, "model", self.model)
        if response.stop_reason == "refusal":
            return Answer("", model, calls, refused=True)
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        return Answer(text, model, calls, stopped_early=response.stop_reason == "tool_use")


# ---------- OpenAI, Azure OpenAI, Gemini (OpenAI-compatible Chat Completions) ----------

def _gemini_schema(schema):
    """Gemini's compatibility layer accepts a narrower schema: no type unions, no additionalProperties."""
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k == "additionalProperties":
                continue
            if k == "type" and isinstance(v, list):
                kinds = [t for t in v if t != "null"]
                out["type"] = kinds[0] if kinds else "string"
                if "null" in v:
                    out["nullable"] = True
            else:
                out[k] = _gemini_schema(v)
        return out
    if isinstance(schema, list):
        return [_gemini_schema(x) for x in schema]
    return schema


class OpenAICompatProvider:
    def __init__(self, name: str, model: str, client=None):
        self.name, self.model = name, model
        self._client = client

    def client(self):
        if self._client is None:
            import openai
            common = {"timeout": 40.0, "max_retries": 1}
            if self.name == "azure":
                self._client = openai.AzureOpenAI(api_key=config.AZURE_OPENAI_API_KEY,
                                                  azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
                                                  api_version=config.AZURE_OPENAI_API_VERSION, **common)
            elif self.name == "gemini":
                self._client = openai.OpenAI(api_key=config.GEMINI_API_KEY, base_url=GEMINI_BASE_URL, **common)
            else:
                self._client = openai.OpenAI(api_key=config.OPENAI_API_KEY, **common)
        return self._client

    def _tools(self, tools: list[dict]) -> list[dict]:
        out = []
        for t in tools:
            params = t["input_schema"]
            fn = {"name": t["name"], "description": t["description"], "parameters": params}
            if self.name == "gemini":
                fn["parameters"] = _gemini_schema(params)
            else:
                fn["strict"] = True  # schemas already list every property and forbid extras
            out.append({"type": "function", "function": fn})
        return out

    def run(self, system: str, tools: list[dict], messages: list[dict], execute: Executor, deadline: float) -> Answer:
        import openai

        msgs = [{"role": "system", "content": system}, *messages]
        fn_tools = self._tools(tools)
        # Newer OpenAI / Azure models only accept max_completion_tokens; Gemini's layer uses max_tokens.
        limit = {"max_tokens": MAX_OUTPUT_TOKENS} if self.name == "gemini" else {"max_completion_tokens": MAX_OUTPUT_TOKENS}
        calls, choice, response = [], None, None
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                if time.monotonic() > deadline:
                    break
                response = self.client().chat.completions.create(model=self.model, messages=msgs, tools=fn_tools, **limit)
                choice = response.choices[0]
                tool_calls = choice.message.tool_calls or []
                if not tool_calls:
                    break
                msgs.append({"role": "assistant", "content": choice.message.content,
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                            for tc in tool_calls]})
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                        out = execute(tc.function.name, args if isinstance(args, dict) else {})
                    except json.JSONDecodeError:
                        args, out = {}, {"error": "Tool arguments were not valid JSON."}
                    calls.append({"tool": tc.function.name, "input": args})
                    msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out, default=str)[:30_000]})
        except openai.RateLimitError:
            raise LLMError(429, "The AI service is busy. Try again in a minute.")
        except openai.APITimeoutError:
            raise LLMError(504, "The AI investigator took too long. Try a narrower question.")
        except openai.APIConnectionError:
            raise LLMError(502, "Couldn't reach the AI service.")
        except openai.APIStatusError as e:
            raise LLMError(502, f"AI service error ({e.status_code}).")

        if choice is None:
            raise LLMError(504, "The AI investigator took too long.")
        model = getattr(response, "model", None) or self.model
        if choice.finish_reason == "content_filter" or getattr(choice.message, "refusal", None):
            return Answer("", model, calls, refused=True)
        return Answer((choice.message.content or "").strip(), model, calls,
                      stopped_early=bool(choice.message.tool_calls))

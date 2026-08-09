#!/usr/bin/env python3
"""Provider selection, config namespacing, and the SSRF guard.

    python3 tests/test_providers.py

Applies the edibl chat-and-providers spec to BKON. The three things the spec
says are "where the bodies are buried" get the coverage: never send a secret to
the wrong endpoint (per-provider namespacing), never trust a user base URL (SSRF
guard), and a misconfigured provider fails loudly rather than half-working.

Adapters lazy-import their SDKs, so building a provider must NOT require the SDK
installed -- only actually calling it would. That is asserted here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "lightrag_service"))

from providers.base import ProviderError            # noqa: E402
from providers.config import build_provider, llm_url_ok  # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


print("SSRF guard — the base URL you must never trust")
check("no url is fine (vendor default)", llm_url_ok(None), True)
check("loopback allowed", llm_url_ok("http://127.0.0.1:11434"), True)
check("localhost name allowed", llm_url_ok("http://localhost:9621"), True)
check("LAN allowed", llm_url_ok("http://192.168.1.50:11434"), True)
check("a real DNS name allowed", llm_url_ok("https://ollama.com"), True)
check("cloud metadata REFUSED", llm_url_ok("http://169.254.169.254/latest"), False)
check("link-local REFUSED", llm_url_ok("http://[fe80::1]/"), False)
check("ipv4-mapped metadata REFUSED",
      llm_url_ok("http://[::ffff:169.254.169.254]/"), False)

print("\nprovider selection")
p = build_provider({"AI_PROVIDER": "ollama", "OLLAMA_MODEL": "gpt-oss:120b",
                    "OLLAMA_API_KEY": "k"})
check("ollama builds", p.name, "ollama")
check("and is available", p.available(), True)

p = build_provider({"AI_PROVIDER": "anthropic",
                    "ANTHROPIC_API_KEY": "sk-ant", "ANTHROPIC_MODEL": "claude-sonnet-5"})
check("anthropic builds", p.name, "anthropic")

p = build_provider({"AI_PROVIDER": "openai", "OPENAI_MODEL": "gpt-4o-mini",
                    "OPENAI_API_KEY": "sk", "OPENAI_BASE_URL": "https://api.groq.com/openai/v1"})
check("openai-compatible builds with a custom base url", p.name, "openai")

print("\nper-provider namespacing — a key for one vendor never reaches another")
# Only the anthropic key is set; selecting ollama must not silently borrow it.
try:
    build_provider({"AI_PROVIDER": "anthropic", "OLLAMA_MODEL": "x"})
    check("anthropic without its own key is refused", False, True)
except ProviderError:
    check("anthropic without its own key is refused", True, True)

print("\nmisconfiguration fails loudly")
def err(env):
    try: build_provider(env); return None
    except ProviderError as e: return str(e)
check("unknown provider named", "Unknown AI_PROVIDER" in (err({"AI_PROVIDER": "gemini"}) or ""), True)
check("anthropic needs a key",
      "not fully configured" in (err({"AI_PROVIDER": "anthropic", "ANTHROPIC_MODEL": "m"}) or ""), True)
check("SSRF base url refused at build",
      "link-local" in (err({"AI_PROVIDER": "ollama", "OLLAMA_MODEL": "m",
                            "OLLAMA_BASE_URL": "http://169.254.169.254"}) or ""), True)

print("\nbuilding a provider does not require its SDK installed (lazy import)")
# anthropic/openai SDKs are not installed in this test env; building must work.
try:
    build_provider({"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k",
                    "ANTHROPIC_MODEL": "claude-sonnet-5"})
    check("anthropic builds without the sdk present", True, True)
except ImportError:
    check("anthropic builds without the sdk present", False, True)

print("\na reasoning model that only thinks is still answered")
import asyncio
import providers.ollama as _oll

def run(c): return asyncio.get_event_loop().run_until_complete(c)
class _FakeClient:
    """Returns a scripted sequence of messages, one per call."""
    def __init__(self, msgs, done="stop", reject_think=False):
        self._m = list(msgs) if isinstance(msgs, list) else [msgs]
        self._d = done; self._reject = reject_think
        self.calls = []
    async def chat(self, **kw):
        self.calls.append(kw)
        if self._reject and "think" in kw:
            raise RuntimeError("model does not support think")
        m = self._m.pop(0) if len(self._m) > 1 else self._m[0]
        return {"message": m, "done_reason": self._d}

def _with(msgs, done="stop", reject_think=False):
    p = _oll.OllamaProvider("http://x", "gpt-oss:20b")
    p._client = _FakeClient(msgs, done, reject_think)
    return p

p = _with({"content": "hello"})
check("normal content is returned", run(p.complete("hi")), "hello")
# The root fix: ask the model not to reason, so the answer lands in `content`
# where every other provider puts it.
check("thinking is switched off", p._client.calls[0].get("think"), False)

# A model that rejects the parameter is asked again without it, not failed.
p = _with({"content": "hello"}, reject_think=True)
check("a model that rejects `think` still answers", run(p.complete("hi")), "hello")
check("and the retry drops the parameter", "think" in p._client.calls[1], False)

check("content still wins when both are present",
      run(_with({"content": "final", "thinking": "musing"}).complete("hi")), "final")
# If the model wrote the JSON into its deliberation anyway, take the JSON --
# but only the JSON. Returning raw chain-of-thought shows the user "We need to
# call the tool." in place of an answer, which is worse than an error.
check("JSON is salvaged out of the deliberation",
      run(_with({"content": "",
                 "thinking": 'We should call it. {"tool":"lint_recipe"} yes'}
                ).complete("hi")),
      '{"tool":"lint_recipe"}')
# An empty turn is intermittent -- the same prompt succeeds on a retry -- so an
# empty response is asked again rather than failed. This is the behaviour that
# actually keeps the studio usable on a reasoning model.
p = _with([{"content": ""}, {"content": "second time lucky"}])
check("an empty turn is retried", run(p.complete("hi")), "second time lucky")
check("and the retry asks a different way",
      (p._client.calls[0].get("think"), "think" in p._client.calls[1]), (False, False))

p = _with({"content": "", "thinking": "We need to call the tool."})
try:
    run(p.complete("hi"))
    check("prose-only deliberation raises rather than being shown", False, True)
except _oll.ProviderError as ex:
    check("prose-only deliberation raises rather than being shown", True, True)
    check("only after three attempts", len(p._client.calls), 3)
    check("and the error suggests a fix", "non-reasoning" in str(ex), True)
try:
    run(_with({"content": "", "thinking": ""}).complete("hi"))
    check("a wholly silent model raises rather than returning ''", False, True)
except _oll.ProviderError:
    check("a wholly silent model raises rather than returning ''", True, True)

print("\nevery provider can say which model it is using")
# The status page reads .model. It used to read an attribute that did not
# exist and show None, which is how a UI-saved model quietly shadowing the
# configured one went unnoticed.
import providers.anthropic as _ant, providers.openai_compat as _oai
check("ollama reports its model",
      _oll.OllamaProvider("http://x", "gpt-oss:120b").model, "gpt-oss:120b")
check("anthropic reports its model",
      _ant.AnthropicProvider("k", "claude-sonnet-5").model, "claude-sonnet-5")
check("openai reports its model",
      _oai.OpenAICompatProvider("k", "gpt-4o").model, "gpt-4o")

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

#!/usr/bin/env python3
"""LightRAG backend + fallback.

    python3 tests/test_rag_backend.py

The rule under test: the upgrade can never become a downgrade. Whatever the
LightRAG server does -- 500, timeout, empty body, wrong key, changed response
shape -- questions must keep working by falling back to the local retriever.
The HTTP session is faked, so this needs no aiohttp and no server.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import rag_backend as RB  # noqa: E402
from bkon_brewer.knowledge import KnowledgeBase, Passage  # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


def run(c): return asyncio.get_event_loop().run_until_complete(c)


class FakeResp:
    def __init__(self, status=200, body=None, raises=None):
        self.status = status; self._body = body; self._raises = raises
    async def __aenter__(self):
        if self._raises: raise self._raises
        return self
    async def __aexit__(self, *a): return False
    async def json(self): return self._body
    async def text(self): return str(self._body)


class FakeSession:
    """Records the last request and returns a scripted response."""
    def __init__(self, resp): self._resp = resp; self.last = None
    def post(self, url, json=None, headers=None, timeout=None):
        self.last = {"url": url, "json": json, "headers": headers}
        return self._resp
    def get(self, url, headers=None, timeout=None):
        self.last = {"url": url, "headers": headers}
        return self._resp


LOCAL = KnowledgeBase([
    Passage("RAIN Guide", 4, "Deeper vacuums make a stronger brew."),
])


print("request building")
be = RB.LightRagBackend("http://ollama-box:9621/", api_key="secret", mode="hybrid")
check("trailing slash trimmed", be.base_url, "http://ollama-box:9621")
sess = FakeSession(FakeResp(200, {"response": "Use a deeper vacuum."}))
ans = run(be.async_answer(sess, "how do I make it stronger"))
check("hits /query", sess.last["url"], "http://ollama-box:9621/query")
check("sends the mode", sess.last["json"]["mode"], "hybrid")
check("sends the query", sess.last["json"]["query"], "how do I make it stronger")
check("carries the api key", sess.last["headers"]["X-API-Key"], "secret")
check("returns the answer", ans, "Use a deeper vacuum.")

print("\ninvalid mode falls back to hybrid")
check("bad mode corrected", RB.LightRagBackend("x", mode="nonsense").mode, "hybrid")

print("\nresponse-shape tolerance (survives a server upgrade)")
for shape, val in (({"answer": "A"}, "A"), ({"data": "B"}, "B"),
                   ("bare string", "bare string"), ({"result": "C"}, "C")):
    s = FakeSession(FakeResp(200, shape))
    check(f"reads {type(shape).__name__} shape", run(be.async_answer(s, "q")), val)

print("\nfailures raise RagError (so the caller can fall back)")
def raises(coro):
    try: run(coro); return None
    except RB.RagError as e: return e
check("500 raises", raises(be.async_answer(FakeSession(FakeResp(500)), "q")) is not None, True)
check("401 raises with a key hint",
      "API key" in str(raises(be.async_answer(FakeSession(FakeResp(401)), "q"))), True)
check("empty answer raises",
      raises(be.async_answer(FakeSession(FakeResp(200, {"response": ""})), "q")) is not None, True)
check("connection error raises",
      raises(be.async_answer(FakeSession(FakeResp(raises=OSError("refused"))), "q")) is not None, True)

print("\nfallback: the upgrade never becomes a downgrade")
good = FakeSession(FakeResp(200, {"response": "graph answer"}))
text, src = run(RB.answer_with_fallback(good, be, LOCAL, "vacuum"))
check("uses lightrag when healthy", (text, src), ("graph answer", "lightrag"))
down = FakeSession(FakeResp(503))
text, src = run(RB.answer_with_fallback(down, be, LOCAL, "vacuum"))
check("falls back to local on failure", src, "local")
check("and the local answer is real", "stronger brew" in text, True)
text, src = run(RB.answer_with_fallback(None, None, LOCAL, "vacuum"))
check("no backend configured -> local", src, "local")
text, src = run(RB.answer_with_fallback(None, None, KnowledgeBase([]), "q"))
check("no backend and empty index -> honest message", src, "none")

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

#!/usr/bin/env python3
"""Auth for the LightRAG service.

    python3 tests/test_service_contract.py

The service sits between the integration and the cloud LLM, so its gate matters.
Tested in isolation from the heavy service imports (lightrag, fastembed) -- the
auth decision is a pure function over headers and must be provable with nothing
installed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "lightrag_service"))

from contract import authorized, clean_answer   # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


print("api key accepted either way the integration might send it")
check("X-API-Key header", authorized("secret", None, "secret"), True)
check("Authorization: Bearer", authorized(None, "Bearer secret", "secret"), True)
check("bearer is case-insensitive on the scheme",
      authorized(None, "bearer secret", "secret"), True)

print("\nwrong or missing key is refused")
check("wrong X-API-Key", authorized("nope", None, "secret"), False)
check("wrong bearer", authorized(None, "Bearer nope", "secret"), False)
check("no credentials at all", authorized(None, None, "secret"), False)
check("length mismatch refused", authorized("sec", None, "secret"), False)

print("\nauth disabled when no key is configured (an explicit operator choice)")
check("empty expected -> open", authorized(None, None, ""), True)
check("empty expected -> open even with junk", authorized("x", None, ""), True)

print("\nanswer cleanup")
check("strips an Answer: prefix", clean_answer("Answer: use a deeper vacuum"),
      "use a deeper vacuum")
check("leaves a normal answer alone", clean_answer("Use a deeper vacuum."),
      "Use a deeper vacuum.")
check("handles empty", clean_answer(""), "")

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

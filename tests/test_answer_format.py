#!/usr/bin/env python3
"""What reaches the reader: LightRAG's boilerplate removed, tables intact.

    python3 tests/test_answer_format.py

LightRAG ends an answer with its own reference list — "[1] Vacuum Leak (Document
Chunks 1-8)", "(Knowledge Graph)". Those name internal retrieval artefacts, not
anything a person can open, and the UI shows real looked-up citations already.
Showing both is confusing; showing the useless one is worse.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "lightrag_service"))
from contract import clean_answer                # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")
def ok(n, c): check(n, bool(c), True)

REAL = """Possible reasons the brewer is not pulling a vacuum.

| # | Likely cause | What to check |
|---|--------------|---------------|
| 1 | Vacuum pump not operating | Verify power. <br>Inspect wiring. |

---
### References

* [1] Vacuum Leak-Negative Pressure Test (Document Chunks 1-8)
* [2] Mainboard Software (Knowledge Graph)
* [3] Check Valve (Knowledge Graph)
"""

print("LightRAG's own reference block is removed")
out = clean_answer(REAL)
ok("the heading goes", "References" not in out)
ok("the entries go", "Knowledge Graph" not in out and "Document Chunks" not in out)

print("\nbut the answer itself survives intact")
ok("the prose stays", "not pulling a vacuum" in out)
ok("the table stays", "| 1 | Vacuum pump not operating" in out)
ok("the table header stays", "| # | Likely cause" in out)
ok("cell line breaks stay", "<br>" in out)

print("\ninline markers pointing at the removed list go too")
check("a bare marker is dropped", clean_answer("Check the pump [1] and the valve [2]."),
      "Check the pump and the valve.")
ok("but a range like [1-8] inside prose is untouched",
   "[1-8]" in clean_answer("See figures [1-8] for detail."))

print("\na section that is genuinely about sources is left alone")
prose = ("Answer.\n\n## Sources\nThe pump draws from the reservoir, which is why "
         "the check valve matters here.")
ok("prose under a Sources heading survives", "reservoir" in clean_answer(prose))

print("\nthe ordinary cases still work")
check("Answer: prefix", clean_answer("Answer: it descales."), "it descales.")
check("empty is safe", clean_answer(""), "")
check("None is safe", clean_answer(None), "")

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

#!/usr/bin/env python3
"""Knowledge-base retrieval.

    python3 tests/test_knowledge.py

Uses a tiny synthetic index, NOT the real documents -- the ranking logic is what
is under test, and it must be provable without shipping anyone's manuals. The
real index is built locally by scripts/build_kb.py and never committed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer.knowledge import KnowledgeBase, Passage   # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


# Synthetic passages that stand in for real documents. Distinct topics so the
# ranker's job -- pick the right one -- is unambiguous.
KB = KnowledgeBase([
    Passage("Descaling Guide", 1,
            "Run the quarterly descaling procedure using the descaler tablet. "
            "Empty and rinse the pitcher when descaling finishes."),
    Passage("Error Codes", 2,
            "Chamber not sealed means the brew chamber glass is not seated. "
            "Check the chamber is closed before brewing."),
    Passage("Installation Manual", 3,
            "The water supply needs 30 to 90 psi input pressure and a 3/8 inch "
            "connection with a shut-off valve."),
    Passage("RAIN Guide", 4,
            "Vacuum strength is measured in kilopascals. Deeper vacuums and "
            "longer steep times produce a stronger, more concentrated brew."),
])


print("retrieval picks the on-topic document")
check("descaling", KB.search("how do I descale the machine")[0].passage.doc,
      "Descaling Guide")
check("water pressure", KB.search("what water pressure do I need")[0].passage.doc,
      "Installation Manual")
check("brew strength", KB.search("how do I make it stronger")[0].passage.doc,
      "RAIN Guide")
check("error meaning", KB.search("chamber not sealed error")[0].passage.doc,
      "Error Codes")

print("\nranking and thresholds")
check("returns at most k", len(KB.search("vacuum", k=2)) <= 2, True)
check("off-topic query returns nothing",
      KB.search("bluetooth firmware bootloader xyzzy"), [])
check("empty query is empty", KB.search(""), [])

print("\nanswers cite their source")
ans = KB.answer("how do I descale")
check("names the document", "Descaling Guide" in ans, True)
check("no match is stated plainly, not faked",
      "don't have anything" in KB.answer("quantum flux capacitor"), True)

print("\nempty index degrades gracefully")
empty = KnowledgeBase([])
check("not ready", empty.ready, False)
check("search is empty", empty.search("anything"), [])
check("answer says so", "don't have" in empty.answer("anything"), True)

print("\nfrom_file with a missing path is empty, not an error")
kb = KnowledgeBase.from_file("/nonexistent/kb.json")
check("empty", kb.ready, False)

print("\nmetadata")
check("size", KB.size, 4)
check("document list", KB.documents,
      ["Descaling Guide", "Error Codes", "Installation Manual", "RAIN Guide"])

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

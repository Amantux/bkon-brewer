#!/usr/bin/env python3
"""Concierge routing: customise vs answer vs clarify.

    python3 tests/test_concierge.py

The one call it must get right is telling "make my cup stronger" (change a
recipe) apart from "how do I make coffee stronger" (answer a question) -- both
contain "stronger". When it cannot tell, it must ask, not guess.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import concierge          # noqa: E402
from bkon_brewer.knowledge import KnowledgeBase, Passage  # noqa: E402
from bkon_brewer.protocol import recipe as R  # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


KB = KnowledgeBase([
    Passage("Descaling Guide", 1,
            "Run the quarterly descaling procedure with the descaler tablet."),
    Passage("RAIN Guide", 4,
            "Deeper vacuums and longer steep times make a stronger brew."),
])
RECIPES = {
    "Morning Cup": [R.start(200), R.fill(250, pause_seconds=10), R.vacuum(24, 4)],
    "Espresso Style": [R.start(205), R.vacuum(30, 6)],
}


print("customise vs answer — the distinction that matters")
r = concierge.respond("make my Morning Cup stronger", RECIPES, KB)
check("named recipe + intent -> customise", r.kind, "customise")
check("targets the right recipe", r.recipe_name, "Morning Cup")
check("returns proposed steps", r.new_steps is not None, True)

r = concierge.respond("how do I make coffee stronger?", RECIPES, KB)
check("question shape -> answer", r.kind, "answer")
check("answers from the docs", "RAIN Guide" in r.text, True)

print("\nrecipe reference without a name")
r = concierge.respond("make it hotter", {"Only One": [R.start(200)]}, KB)
check("single recipe, no ambiguity -> customise", r.kind, "customise")
r = concierge.respond("make it hotter", RECIPES, KB)
check("several recipes -> ask which", r.kind, "clarify")
check("lists the options", "Morning Cup" in r.text and "Espresso Style" in r.text, True)

print("\nplain questions go to the knowledge base")
r = concierge.respond("how do I descale?", RECIPES, KB)
check("descale question answered", "Descaling Guide" in r.text, True)
r = concierge.respond("what does a vacuum do", RECIPES, KB)
check("no '?' but question word still routes to answer", r.kind, "answer")

print("\ncustomisation does not mutate the stored recipe")
before = int(RECIPES["Morning Cup"][2].values["ps"])
concierge.respond("make Morning Cup stronger", RECIPES, KB)
check("original recipe untouched",
      int(RECIPES["Morning Cup"][2].values["ps"]), before)

print("\nfaults and error codes route to diagnosis, composed so the service keeps it")
r = concierge.respond("it says not sealed", RECIPES, KB)
check("fault -> composed answer", r.composed, True)
check("with a fix", "seat" in r.text.lower() or "seal" in r.text.lower(), True)
r = concierge.respond("what does C:3 M:5 mean", RECIPES, KB)
check("error code -> composed", r.composed, True)
r = concierge.respond("how do I descale?", RECIPES, KB)
check("a plain document question is NOT composed (goes to RAG)", r.composed, False)

print("\ngraceful degradation")
r = concierge.respond("how do I descale?", RECIPES, KnowledgeBase([]))
check("no index -> says so, does not crash", "don't have the BKON documents" in r.text, True)
r = concierge.respond("", RECIPES, KB)
check("empty message -> clarify", r.kind, "clarify")

print("\nan adjustment when no recipes exist yet")
r = concierge.respond("make it stronger", {}, KB)
check("nothing to adjust routes somewhere sane",
      r.kind in ("clarify", "answer"), True)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

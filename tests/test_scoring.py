#!/usr/bin/env python3
"""LLM recipe critique.

    python3 tests/test_scoring.py

The score is the model's, but the facts handed to it are computed here and must
be right -- byte size, fit, lint problems -- so a fake provider that echoes a
scripted critique exercises the real prompt-building, parsing and coercion
without a model. Mirrors the chat-loop test.
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "lightrag_service"))

import scoring as S                                  # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")
def ok(n, c): check(n, bool(c), True)
def run(c): return asyncio.get_event_loop().run_until_complete(c)


class Fake:
    """Returns a scripted reply, and remembers the prompt it was given."""
    def __init__(self, reply): self.reply = reply; self.prompt = None; self.system = None
    async def complete(self, prompt, system=None):
        self.prompt = prompt; self.system = system; return self.reply


GOOD = [
    {"type": "start", "values": {"tmp": "205"}},
    {"type": "fr", "values": {"fwv": "250", "rwv": "30"}},
    {"type": "vc", "values": {"ps": "24", "tm": "6"}},
    {"type": "pg", "values": {"ps": "30", "tm": "10", "det": "1"}},
]

print("the facts handed to the model are computed, not guessed")
f = S.facts_for(GOOD)
ok("counts the steps", f["step_count"] == 4)
ok("measures the wire size", f["bytes"] > 0)
ok("knows it fits Bluetooth", f["fits_bluetooth"] is True)
ok("a clean recipe has no problems", f["problems"] == [])

bad = [{"type": "start", "values": {"tmp": "205"}},
       {"type": "pg", "values": {"ps": "50", "tm": "10"}}]   # 50 is out of 25-35
p = S.facts_for(bad)
ok("the linter's findings are passed through", any("purge" in x.lower() for x in p["problems"]))

print("\na scripted critique parses into a Critique")
reply = json.dumps({"score": 82, "verdict": "Solid everyday cup",
                    "comment": "Good use of the vacuum. A touch light.",
                    "dimensions": [{"name": "Extraction", "rating": 4, "comment": "24 kPa, 6 s"},
                                   {"name": "Fit", "rating": 5, "comment": "well under 599"}],
                    "suggestions": ["Deepen the vacuum ~2 kPa", "Lengthen the steep to 8 s"]})
c = run(S.score_recipe(Fake(reply), GOOD))
check("the score comes through", c.score, 82)
check("the verdict comes through", c.verdict, "Solid everyday cup")
check("dimensions parse", [d.name for d in c.dimensions], ["Extraction", "Fit"])
check("dimension ratings parse", [d.rating for d in c.dimensions], [4, 5])
check("suggestions parse", len(c.suggestions), 2)
ok("the facts ride along on the critique", c.facts["bytes"] > 0)

print("\nthe model is grounded with the recipe and the facts")
fk = Fake(reply); run(S.score_recipe(fk, GOOD))
ok("the recipe is in the prompt", "vc" in fk.prompt and "205" in fk.prompt)
ok("the byte fit is in the prompt", "599" in fk.prompt)
ok("the confirmed ranges are in the prompt", "140-212" in fk.prompt)
ok("the system prompt asks for JSON only", "JSON" in fk.system)

print("\nbad model output degrades safely, never throws")
c = run(S.score_recipe(Fake("I think it's pretty good, maybe a 7/10."), GOOD))
check("prose becomes the comment", c.comment, "I think it's pretty good, maybe a 7/10.")
check("an unscored critique is labelled", c.verdict, "Unscored")
# out-of-range / wrong-typed fields are coerced, not trusted
c = run(S.score_recipe(Fake('{"score": 999, "dimensions": [{"name":"X","rating":"nine"}]}'), GOOD))
check("score is clamped to 0-100", c.score, 100)
check("a bad rating falls back to the middle", c.dimensions[0].rating, 3)

print("\nan empty recipe is scoreable, not a crash")
c = run(S.score_recipe(Fake('{"score": 0, "verdict": "Empty"}'), []))
check("empty scores", c.score, 0)
ok("empty has zero bytes", c.facts["bytes"] == 0)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

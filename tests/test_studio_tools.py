#!/usr/bin/env python3
"""The recipe studio's tools, and the chat feedback loop that drives them.

    python3 tests/test_studio_tools.py

test_chat.py covers the loop with fake tools; this covers the real ones -- the
integration's own build / tune / lint / diagnose logic, vendored into the add-on
-- and the round trip the browser actually performs: send steps, get changed
steps back, send those again. A scripted provider stands in for the model, so
the assertions are about the recipe changing, not about a model's wording.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "lightrag_service"))

import chat as C                                     # noqa: E402
import studio_tools as T                             # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")

def ok(n, cond): check(n, bool(cond), True)
def run(c): return asyncio.get_event_loop().run_until_complete(c)


class Scripted:
    def __init__(self, replies): self._r = list(replies); self.systems = []
    async def complete(self, prompt, system=None):
        self.systems.append(system or "")
        return self._r.pop(0)


def vac(steps):   # strongest vacuum in the recipe
    return max((int(s["values"]["ps"]) for s in steps if s["type"] == "vc"), default=None)
def temp(steps):
    return next((int(s["values"]["tmp"]) for s in steps if s["type"] == "start"), None)
def steep(steps):
    return max((int(s["values"]["tm"]) for s in steps if s["type"] == "vc"), default=None)


print("the tools speak the same step dicts the browser sends")
_, built = T.build_recipe({"description": "a strong cup"}, [])
ok("steps are plain dicts", all(isinstance(s, dict) for s in built))
ok("type and values only", all(set(s) == {"type", "values"} for s in built))
ok("values are strings, as the wire wants",
   all(isinstance(v, str) for s in built for v in s["values"].values()))
ok("round-trips back in unchanged", T.lint_recipe({}, built)[0]["ok"] is True)

print("\nfeedback actually moves the recipe")
res, stronger = T.adjust_recipe({"feedback": "make it stronger"}, built)
ok("reported as changed", res["changed"])
ok("the vacuum deepened", vac(stronger) > vac(built))
ok("the summary says what moved", "acuum" in res["summary"] or "teep" in res["summary"])

res, cooler = T.adjust_recipe({"feedback": "less bitter"}, built)
ok("less bitter drops the temperature", temp(cooler) < temp(built))

res, longer = T.adjust_recipe({"feedback": "slower"}, built)
ok("slower lengthens the steep", steep(longer) > steep(built))

print("\nfeedback it cannot parse leaves the recipe alone")
res, unchanged = T.adjust_recipe({"feedback": "make it purple"}, built)
check("not reported as changed", res["changed"], False)
check("no new steps handed back", unchanged, None)
ok("and it says so", "could not" in res["summary"].lower() or "not tell" in res["summary"].lower())

print("\nthe full chat round trip: build, then tune by feedback")
p = Scripted(['{"tool":"build_recipe","args":{"description":"a strong small cup"}}',
              '{"answer":"Built it."}'])
turn1 = run(C.run_chat(p, "build a strong small cup", [], dict(T.REGISTRY)))
ok("a recipe came back", turn1.steps and len(turn1.steps) > 1)

# The browser now holds turn1.steps and sends them with the next message.
p = Scripted(['{"tool":"adjust_recipe","args":{"feedback":"less bitter please"}}',
              '{"answer":"Eased the bitterness."}'])
turn2 = run(C.run_chat(p, "less bitter please", turn1.steps, dict(T.REGISTRY)))
ok("the tune ran on the built recipe", [a.tool for a in turn2.actions] == ["adjust_recipe"])
ok("the temperature came down", temp(turn2.steps) < temp(turn1.steps))
ok("step count is stable", len(turn2.steps) == len(turn1.steps))

# ...and again, proving state carries across turns rather than resetting.
p = Scripted(['{"tool":"adjust_recipe","args":{"feedback":"stronger"}}',
              '{"answer":"Deepened the vacuum."}'])
turn3 = run(C.run_chat(p, "stronger", turn2.steps, dict(T.REGISTRY)))
ok("still cooler from turn 2", temp(turn3.steps) < temp(turn1.steps))
ok("and now stronger too", vac(turn3.steps) > vac(turn1.steps))

print("\nlint and diagnose reach the real logic")
r, _ = T.lint_recipe({}, [{"type": "vc", "values": {"ps": "24", "tm": "4"}}])
ok("a recipe with no start is flagged", r["problem_count"] > 0)
r, _ = T.diagnose({"text": "C:3 M:5"}, [])
ok("a known code is explained", "seal" in (r["cause"] or "").lower())

print("\nthe LightRAG toggle decides whether documents are offered at all")
docs_tool = lambda a, s: ({"answer": "..."}, None)
on = T.registry_for(docs_tool)
off = T.registry_for(None)
ok("documents tool present when the RAG is on", "answer_docs" in on)
check("absent when it is off", "answer_docs" in off, False)
ok("the recipe tools survive either way",
   all(t in on and t in off for t in T.REGISTRY))
ok("tuning still works with the RAG off",
   T.adjust_recipe({"feedback": "stronger"}, built)[0]["changed"])

with_docs = C.build_system(on)
without = C.build_system(off)
ok("answer_docs offered when the RAG is on", "answer_docs" in with_docs)
check("and never mentioned when it is off", "answer_docs" in without, False)
ok("the recipe tools are always there", all(t in without for t in T.REGISTRY))

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

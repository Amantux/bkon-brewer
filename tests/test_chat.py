#!/usr/bin/env python3
"""The agent chat loop.

    python3 tests/test_chat.py

Per the edibl test guidance: a fake provider (a turn that calls a tool, then
answers) exercises the real loop. No model, no network, no Home Assistant. The
provider and tools are injected, so this is the loop's logic under test, not a
vendor's tool-calling format.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "lightrag_service"))

import chat as C                                    # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")

def run(c): return asyncio.get_event_loop().run_until_complete(c)


class FakeProvider:
    """Returns a scripted sequence of raw model replies."""
    def __init__(self, replies): self._r = list(replies); self.prompts = []
    async def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        return self._r.pop(0)


# Tools operate on (args, steps) -> (result, new_steps_or_None).
def build_tool(args, steps):
    return {"template": "strong", "steps": 4}, [{"type": "start", "values": {"tmp": "205"}}]
def adjust_tool(args, steps):
    new = [dict(s) for s in steps] + [{"type": "vc", "values": {"ps": "26"}}]
    return {"changed": True, "summary": "deepened vacuum"}, new
def lint_tool(args, steps):
    return {"ok": True, "problems": []}, None
def diagnose_tool(args, steps):
    return {"summary": "Chamber not sealed", "fix": "reseat"}, None
TOOLS = {"build_recipe": build_tool, "adjust_recipe": adjust_tool,
         "lint_recipe": lint_tool, "diagnose": diagnose_tool}


print("json extraction is tolerant of how models actually reply")
check("bare object", C._extract_json('{"answer":"hi"}'), {"answer": "hi"})
check("fenced", C._extract_json('```json\n{"tool":"lint_recipe","args":{}}\n```'),
      {"tool": "lint_recipe", "args": {}})
check("prose around it", C._extract_json('Sure! {"answer":"ok"} hope that helps'),
      {"answer": "ok"})
check("nested braces", C._extract_json('{"tool":"x","args":{"a":1}}'),
      {"tool": "x", "args": {"a": 1}})
check("no json -> None", C._extract_json("just talking"), None)

print("\na tool call then an answer (the core loop)")
p = FakeProvider(['{"tool":"build_recipe","args":{"description":"strong"}}',
                  '{"answer":"Built you a strong recipe."}'])
turn = run(C.run_chat(p, "build me a strong cup", [], TOOLS))
check("final reply reaches the user", turn.reply, "Built you a strong recipe.")
check("the tool ran", [a.tool for a in turn.actions], ["build_recipe"])
check("the recipe was updated", turn.steps is not None and len(turn.steps) == 1, True)

print("\ntool results carry forward, steps accumulate")
p = FakeProvider(['{"tool":"build_recipe","args":{"description":"x"}}',
                  '{"tool":"adjust_recipe","args":{"feedback":"stronger"}}',
                  '{"answer":"done"}'])
turn = run(C.run_chat(p, "strong then stronger", [], TOOLS))
check("both tools ran in order",
      [a.tool for a in turn.actions], ["build_recipe", "adjust_recipe"])
check("adjust saw the built recipe and extended it", len(turn.steps), 2)

print("\na plain-text reply is treated as the answer, not a crash")
p = FakeProvider(["I think you should descale it."])
turn = run(C.run_chat(p, "help", [], TOOLS))
check("plain text becomes the reply", turn.reply, "I think you should descale it.")
check("no tools claimed", turn.actions, [])

print("\nunknown tool is fed back, the model recovers")
p = FakeProvider(['{"tool":"make_coffee","args":{}}',
                  '{"answer":"recovered"}'])
turn = run(C.run_chat(p, "x", [], TOOLS))
check("recovers to an answer", turn.reply, "recovered")
check("the bad tool did not run", turn.actions, [])
check("the model was told what tools exist", "adjust_recipe" in p.prompts[-1], True)

print("\na tool that raises is caught, not fatal")
def boom(args, steps): raise ValueError("kaboom")
p = FakeProvider(['{"tool":"boom","args":{}}', '{"answer":"handled"}'])
turn = run(C.run_chat(p, "x", [], {"boom": boom}))
check("turn survives a throwing tool", turn.reply, "handled")
check("the error was recorded", turn.actions[0].result.get("error"), "kaboom")

print("\nthe loop cannot run forever")
p = FakeProvider(['{"tool":"lint_recipe","args":{}}'] * 10)
turn = run(C.run_chat(p, "x", [{"type": "start", "values": {}}], TOOLS, max_iters=3))
check("bounded, still returns a reply", isinstance(turn.reply, str) and turn.reply != "", True)
check("ran at most max_iters tools", len(turn.actions) <= 3, True)

print("\nthe current recipe is given to the model as context")
p = FakeProvider(['{"answer":"ok"}'])
run(C.run_chat(p, "hi", [{"type": "vc", "values": {"ps": "24"}}], TOOLS))
check("recipe context is in the prompt", "vc" in p.prompts[0], True)

print("\na blank completion is never shown to the user")
# Reasoning models can finish a turn having written only deliberation, leaving
# the content empty. Rendering that "" is an empty bubble -- indistinguishable
# from a crash. The loop nudges once and, failing that, says what happened.
t = run(C.run_chat(FakeProvider(["", '{"answer":"here it is"}']), "hi", [], {}))
check("a blank is retried, not rendered", t.reply, "here it is")

t = run(C.run_chat(FakeProvider(['{"answer":""}', '{"answer":"a real one"}']), "hi", [], {}))
check("an empty answer field is retried too", t.reply, "a real one")

# A small model handed a template sometimes sends the template back. An
# angle-bracketed stub on screen looks like the app produced it, not the model.
t = run(C.run_chat(FakeProvider(['{"answer":"<your message to the user>"}',
                                 '{"answer":"the actual answer"}']), "hi", [], {}))
check("the example echoed back is retried", t.reply, "the actual answer")
check("but a real answer containing < is left alone",
      run(C.run_chat(FakeProvider(['{"answer":"use <30 kPa here"}']), "hi", [], {})).reply,
      "use <30 kPa here")

t = run(C.run_chat(FakeProvider(["", "", "", "", ""]), "hi", [], {}))
check("never blank, even when the model never speaks", t.reply.strip() != "", True)
check("and it says what to do", "different way" in t.reply, True)

# A turn that did real work before going quiet should still report the work.
called = []
def _t(a, s):
    called.append(1)
    return {"ok": True}, None
t = run(C.run_chat(FakeProvider(['{"tool":"lint_recipe","args":{}}', "", "", "", ""]),
                   "check", [], {"lint_recipe": _t}))
check("a silent turn still names the tools it ran", "lint_recipe" in t.reply, True)

print("\nthe turn reports its steps in order, so the browser can list them")
# The browser turns these into the visible trace. What matters is that each
# report arrives before the thing it describes, and that a step is finished
# exactly when the next one starts -- that pairing is what lets the trace tick
# off completed steps without the server tracking completion itself.
seen = []
def _lint(a, st): return {"ok": True}, None
def _docs(a, st): return {"answer": "descale it"}, None
t = run(C.run_chat(FakeProvider(['{"tool":"answer_docs","args":{"query":"descale"}}',
                                 '{"tool":"lint_recipe","args":{}}',
                                 '{"answer":"done"}']),
                   "how do I descale", [], {"lint_recipe": _lint, "answer_docs": _docs},
                   on_step=lambda k, n="": seen.append((k, n))))
check("thinking is reported before each model call, tools before each tool",
      seen, [("thinking", ""), ("tool", "answer_docs"),
             ("thinking", ""), ("tool", "lint_recipe"),
             ("thinking", "")])
check("and the turn itself is unaffected", t.reply, "done")
check("the actions match the reported tools",
      [a.tool for a in t.actions], ["answer_docs", "lint_recipe"])

# A turn with no tools still reports, so the trace is never empty.
seen = []
run(C.run_chat(FakeProvider(['{"answer":"just an answer"}']), "hi", [], {},
               on_step=lambda k, n="": seen.append(k)))
check("a toolless turn still reports thinking", seen, ["thinking"])

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

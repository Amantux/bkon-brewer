#!/usr/bin/env python3
"""Feedback-driven recipe customisation.

    python3 tests/test_advisor.py

This is the judgement most worth pinning down: what "stronger" or "less bitter"
actually does to a recipe. Grounded in the RAIN guide (docs/INTEL.md), bounded
to the documented ranges, and here proven to move the right parameters in the
right direction without ever leaving the envelope.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import advisor as A       # noqa: E402
from bkon_brewer.protocol import recipe as R  # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


def base():
    return [R.start(200), R.fill(250, rinse_volume_ml=30, pause_seconds=10),
            R.vacuum(24, 4), R.purge(50, 10)]


def val(steps, typ, key):
    for s in steps:
        if s.type == typ:
            return int(s.values[key])
    return None


print("intent parsing")
check("stronger", A.parse_feedback("can you make it stronger"), ["stronger"])
check("multiple intents in one sentence",
      set(A.parse_feedback("stronger and a bit cooler")), {"stronger", "cooler"})
check("synonyms map", A.parse_feedback("too bitter"), ["less_bitter"])
check("word-boundary safe (cool ≠ cooler only)",
      "cooler" in A.parse_feedback("I want it cooler"), True)
check("nothing recognised", A.parse_feedback("hello there"), [])

print("\nstronger deepens vacuum and lengthens steep, within bounds")
c = A.customize(base(), "make it stronger")
check("changed", c.changed, True)
check("vacuum deepened 24 -> 26", val(c.steps, R.StepType.VACUUM, "ps"), 26)
check("fill pause 10 -> 15", val(c.steps, R.StepType.FILL, "ap"), 15)
check("original untouched", val(base(), R.StepType.VACUUM, "ps"), 24)

print("\nweaker is the inverse")
c = A.customize(base(), "a bit lighter please")
check("vacuum eased 24 -> 22", val(c.steps, R.StepType.VACUUM, "ps"), 22)
check("pause shortened 10 -> 5", val(c.steps, R.StepType.FILL, "ap"), 5)

print("\ntemperature moves and clamps to the app's validation range (140-212)")
check("hotter 200 -> 205", val(A.customize(base(), "hotter").steps, R.StepType.START, "tmp"), 205)
check("cooler 200 -> 195", val(A.customize(base(), "cooler").steps, R.StepType.START, "tmp"), 195)
hot = [R.start(210), R.vacuum(24, 4)]
check("clamps at 212 max", val(A.customize(hot, "hotter").steps, R.StepType.START, "tmp"), 212)
atmax = [R.start(212), R.vacuum(24, 4)]
c = A.customize(atmax, "hotter")
check("already at 212 makes no change", val(c.steps, R.StepType.START, "tmp"), 212)
check("and reports it could not go further", bool(c.unmet), True)
cold = [R.start(142), R.vacuum(24, 4)]
check("clamps at 140 min", val(A.customize(cold, "cooler").steps, R.StepType.START, "tmp"), 140)

print("\nless bitter eases temperature and steep together")
c = A.customize(base(), "it's too bitter")
check("temp down 200 -> 195", val(c.steps, R.StepType.START, "tmp"), 195)
check("steep down 10 -> 5", val(c.steps, R.StepType.FILL, "ap"), 5)

print("\ncup size")
check("bigger 250 -> 275", val(A.customize(base(), "make it bigger").steps, R.StepType.FILL, "fwv"), 275)
check("smaller 250 -> 225", val(A.customize(base(), "smaller cup").steps, R.StepType.FILL, "fwv"), 225)

print("\ncombined feedback applies every recognised intent")
c = A.customize(base(), "stronger, hotter, and a bigger cup")
check("vacuum up", val(c.steps, R.StepType.VACUUM, "ps"), 26)
check("temp up", val(c.steps, R.StepType.START, "tmp"), 205)
check("fill up", val(c.steps, R.StepType.FILL, "fwv"), 275)
check("three change lines", len([1 for _ in c.changes]) >= 3, True)

print("\nthe result still encodes and fits")
c = A.customize(base(), "much stronger and bigger")
payload = R.validate(c.steps)      # raises if it broke the recipe
check("valid recipe out", isinstance(payload, str), True)

print("\nunrecognised feedback explains itself, changes nothing")
c = A.customize(base(), "make it purple")
check("not understood", c.not_understood, True)
check("no changes", c.changed, False)
check("summary offers guidance", "stronger" in c.summary(), True)

print("\nan intent with no applicable step is reported, not silently dropped")
c = A.customize([R.dialog("hi")], "stronger")
check("no change made", c.changed, False)
check("unmet reason given", bool(c.unmet), True)

print("\nvacuum time never drops below 1 second")
c = A.customize([R.vacuum(24, 2)], "faster")
check("clamped to 1s floor", val(c.steps, R.StepType.VACUUM, "tm"), 1)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

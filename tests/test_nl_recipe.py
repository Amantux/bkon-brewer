#!/usr/bin/env python3
"""Natural language to a recipe.

    python3 tests/test_nl_recipe.py

The interesting behaviour is targeting: a sentence that names a number should
produce a recipe that hits it, and a number the machine cannot do should be
clamped and *said*, never silently accepted. The shapes come from the published
base recipes (docs/INTEL.md), so those are asserted too.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import nl_recipe as N     # noqa: E402
from bkon_brewer.protocol import recipe as R  # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")
def ok(n, c): check(n, bool(c), True)

def temp(c): return next(int(s.values["tmp"]) for s in c.steps if s.type == R.StepType.START)
def vacs(c): return [int(s.values["ps"]) for s in c.steps if s.type == R.StepType.VACUUM]
def steeps(c): return [int(s.values["tm"]) for s in c.steps if s.type == R.StepType.VACUUM]
def fills(c): return [int(s.values.get("fwv", 0)) for s in c.steps if s.type == R.StepType.FILL]

print("it recognises the beverage and uses that base recipe")
check("green tea", N.compile_recipe("a green tea").style, "green tea")
check("black tea", N.compile_recipe("earl grey please").style, "black tea")
check("delicate leaf", N.compile_recipe("a gyokuro").style, "delicate tea")
check("coffee is the default", N.compile_recipe("something nice").style, "coffee")
check("cold brew", N.compile_recipe("a cold brew").style, "cold brew style")

print("\nthe published base numbers are used")
check("green tea starts at 175 F", temp(N.compile_recipe("green tea")), 175)
check("black tea starts at 205 F", temp(N.compile_recipe("black tea")), 205)
ok("hotter black tea starts from a SHALLOWER vacuum than green",
   vacs(N.compile_recipe("black tea"))[0] < vacs(N.compile_recipe("green tea"))[0])
check("delicate leaf gets exactly one vacuum", len(vacs(N.compile_recipe("a delicate sencha"))), 1)

print("\nthe vacuum sequence follows X, X+2, X+1")
v = vacs(N.compile_recipe("black tea"))
check("three vacuums", len(v), 3)
check("the pattern holds", [v[1]-v[0], v[2]-v[0]], [2, 1])

print("\nexplicit numbers in the sentence are honoured")
check("a temperature in F", temp(N.compile_recipe("green tea at 185 F")), 185)
check("a temperature in C is converted", temp(N.compile_recipe("tea at 90 C")), 194)
check("a volume in ml", fills(N.compile_recipe("a coffee, 300 ml"))[0] > 0, True)
ok("a volume in ml is reflected", any(f >= 200 for f in fills(N.compile_recipe("a coffee, 300ml"))))
check("a vacuum in kPa", vacs(N.compile_recipe("coffee at 30 kPa"))[0], 30)
check("a steep in seconds", steeps(N.compile_recipe("coffee with a 12 second steep"))[-1], 12)
check("a vacuum count", len(vacs(N.compile_recipe("coffee with two vacuums"))), 2)
check("a spelled-out count", len(vacs(N.compile_recipe("tea with three vacuums"))), 3)

print("\nqualitative words move the right dial")
ok("stronger deepens the vacuum",
   vacs(N.compile_recipe("a strong coffee"))[0] > vacs(N.compile_recipe("a coffee"))[0])
ok("lighter shallows it",
   vacs(N.compile_recipe("a light coffee"))[0] < vacs(N.compile_recipe("a coffee"))[0])
ok("full-bodied lengthens the steep",
   steeps(N.compile_recipe("a full-bodied coffee"))[-1] > steeps(N.compile_recipe("a coffee"))[-1])
ok("smooth shortens it",
   steeps(N.compile_recipe("a smooth coffee"))[-1] < steeps(N.compile_recipe("a coffee"))[-1])

print("\nsize maps to a volume")
ok("small is less water than large",
   sum(fills(N.compile_recipe("a small coffee"))) < sum(fills(N.compile_recipe("a large coffee"))))

print("\nimpossible targets are clamped AND reported, never silently accepted")
c = N.compile_recipe("coffee at 260 F")
check("temperature clamped to the maximum", temp(c), 212)
ok("and it says so", any("outside" in u for u in c.unmet))
c = N.compile_recipe("coffee at 90 kPa")
check("vacuum clamped", vacs(c)[0], 60)
ok("vacuum reported", any("kPa" in u for u in c.unmet))
c = N.compile_recipe("coffee, 900 ml")
ok("volume reported", any("600" in u for u in c.unmet))

print("\nwhat comes out is always a brewable recipe")
for phrase in ["a strong small green tea at 180F",
               "delicate white tea, two vacuums, 8 second steep",
               "large cold brew 350ml", "", "asdfghjkl"]:
    c = N.compile_recipe(phrase)
    R.validate(c.steps)                       # raises if it could not brew
    ok(f"valid: {phrase!r:46}", c.steps and c.steps[0].type == R.StepType.START)

print("\nthe summary explains what it targeted")
c = N.compile_recipe("a strong green tea at 185 F, 300 ml")
s = c.summary()
ok("names the style", "green tea" in s)
ok("names a target", "185" in s or "300" in s)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

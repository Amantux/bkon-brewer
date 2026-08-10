#!/usr/bin/env python3
"""One recipe, several serving sizes.

    python3 tests/test_sizes.py

The machine's model is three portions per recipe -- the app's editors are laid
out as serving 1 / 2 / 3, and the .bbp format encodes a portion count followed
by named portions. This integration used to take the first portion and drop the
rest, so every recipe the vendor ships arrived here as one size.

What the vendor's own recipes do between sizes is the whole design: Classic
Pour Over is 181/241/301 ml and both tea menus are 188/250/312, which is medium
+/-25% of the FILL VOLUME and nothing else. Temperature, vacuum depth and steep
times are identical across the three. That follows from the documented dial-in
convention -- vacuum sets concentration, steep sets intensity -- so changing
them between sizes would serve a different drink rather than more of the same.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import app_recipe                    # noqa: E402
from bkon_brewer.library import record_from_any       # noqa: E402
from bkon_brewer.protocol import recipe as R          # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


def ok(name, cond):
    check(name, bool(cond), True)


def fills(steps):
    return [int(s.values["fwv"]) for s in steps if s.type == "fr" and s.values.get("fwv")]


print("the sizes are named, and ordered smallest first")
check("three of them", R.PORTION_NAMES, ("small", "medium", "large"))
check("and one is the default", R.DEFAULT_PORTION, "medium")
ok("the .bbp format agrees", R.PORTION_NAMES == __import__(
    "bkon_brewer.protocol.bbp", fromlist=["x"]).PORTIONS)

print("\nscaling reproduces the vendor's own numbers")
# Classic Pour Over ships as 181 / 241 / 301 ml. Deriving the other two from
# the medium has to land on those, or the rule is a guess dressed as a fact.
base = [R.start(200), R.fill(241, rinse_volume_ml=30), R.vacuum(24, 8),
        R.purge(30, 10)]
sizes = R.sizes_from(base)
check("small matches the shipped recipe", fills(sizes["small"]), [181])
check("medium is left alone", fills(sizes["medium"]), [241])
check("large matches the shipped recipe", fills(sizes["large"]), [301])
# The tea menus are 188 / 250 / 312 from the same rule.
tea = R.sizes_from([R.fill(250)])
check("and the tea menu's sizes too",
      [fills(tea[n])[0] for n in R.PORTION_NAMES], [188, 250, 312])

print("\nonly the water changes")
for name in R.PORTION_NAMES:
    st = sizes[name]
    check(f"{name}: temperature untouched",
          [s.values["tmp"] for s in st if s.type == "start"], ["200"])
    check(f"{name}: vacuum untouched",
          [(s.values["ps"], s.values["tm"]) for s in st if s.type == "vc"],
          [(24, 8)])
    check(f"{name}: purge untouched",
          [(s.values["ps"], s.values["tm"]) for s in st if s.type == "pg"],
          [(30, 10)])
check("but the rinse scales with the fill",
      [[int(s.values["rwv"]) for s in sizes[n] if s.type == "fr"][0]
       for n in R.PORTION_NAMES], [22, 30, 38])

print("\nbuilding a small and asking for the set scales up")
from_small = R.sizes_from([R.fill(181)], base="small")
check("the small is what you built", fills(from_small["small"]), [181])
check("and the others come from it",
      [fills(from_small[n])[0] for n in ("medium", "large")], [241, 301])
try:
    R.sizes_from([R.fill(200)], base="grande")
    check("an unknown base is refused", False, True)
except ValueError as ex:
    check("an unknown base is refused", True, True)
    ok("and it says what it expected", "small" in str(ex))

print("\na volume that was set never scales away to nothing")
# A 1 ml rinse scaled down rounds to 0, and 0 means "absent" to the firmware --
# a step that quietly stops rinsing is worse than one that rinses a little.
tiny = R.scale_portion([R.fill(4, rinse_volume_ml=1)], 0.25)
check("a tiny fill survives", int(tiny[0].values["fwv"]), 1)
check("so does a tiny rinse", int(tiny[0].values["rwv"]), 1)
check("but a volume that was zero stays zero",
      int(R.scale_portion([R.fill(200, rinse_volume_ml=0)], 2.0)[0].values["rwv"]), 0)

print("\nreading an app recipe keeps every size")
app = app_recipe.to_app_recipe("Morning", [
    ("small", [{"type": "fr", "values": {"fwv": "181"}}]),
    ("medium", [{"type": "fr", "values": {"fwv": "241"}}]),
    ("large", [{"type": "fr", "values": {"fwv": "301"}}]),
])
check("all three portions come back",
      [n for n, _ in app_recipe.all_portions(app)], ["small", "medium", "large"])
rec = record_from_any(app)
check("the record carries them", sorted(rec["sizes"]), ["large", "medium", "small"])
check("and its steps are the default size",
      rec["steps"], rec["sizes"]["medium"])

print("\na recipe with one portion is a recipe, not a size called 'standard'")
# This shape is what our own export writes. An earlier version recognised no
# size names here, returned early, and left the record with NO steps at all --
# so a single-portion file imported as nothing.
single = app_recipe.to_app_recipe(
    "Plain", [(app_recipe.SINGLE_PORTION_NAME,
               [{"type": "fr", "values": {"fwv": "250"}}])])
rec = record_from_any(single)
ok("it still imports", rec is not None)
ok("with its steps", rec.get("steps"))
check("and no sizes map", "sizes" in rec, False)

print("\nthe two portion constants are not the same thing")
# Both were called DEFAULT_PORTION, in the same package, with different values.
ok("one names a single unnamed portion",
   app_recipe.SINGLE_PORTION_NAME == "standard")
ok("the other says which size is meant by default",
   R.DEFAULT_PORTION == "medium")

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

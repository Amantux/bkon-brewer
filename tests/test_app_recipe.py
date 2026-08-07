#!/usr/bin/env python3
"""App recipe schema conversion.

    python3 tests/test_app_recipe.py

The app stores recipes as a nested object with named portions, and its purge
flags are keyed differently from the wire. This proves the round-trip and the
key aliasing, so a file we write matches the app's shape and a purge does not
lose its flags crossing between forms.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()
from bkon_brewer import app_recipe as A    # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")

print("purge flags alias between storage and wire keys")
app = {"name": "X", "sequences": {"portions": [{"name": "standard",
        "sequences": [{"type": "pg", "values": {"ps": "30", "purgedet": "1",
                                                "purgecontr": "1"}}]}]}}
name, steps = A.from_app_recipe(app)
check("purgedet -> det on read", steps[0]["values"].get("det"), "1")
check("purgecontr -> contr on read", steps[0]["values"].get("contr"), "1")
check("no storage key leaks through", "purgedet" in steps[0]["values"], False)

print("\nround-trip preserves the recipe")
back = A.to_app_recipe(name, [("standard", steps)])
v = back["sequences"]["portions"][0]["sequences"][0]["values"]
check("det -> purgedet on write", v.get("purgedet"), "1")
check("carries the app metadata fields",
      all(k in back for k in ("name", "dsp_name", "description", "sequences")), True)

print("\nportion selection")
multi = {"name": "M", "sequences": {"portions": [
    {"name": "small", "sequences": [{"type": "start", "values": {"tmp": "180"}}]},
    {"name": "large", "sequences": [{"type": "start", "values": {"tmp": "200"}}]}]}}
check("names listed", A.portions_of(multi), ["small", "large"])
check("default picks first", A.from_app_recipe(multi)[1][0]["values"]["tmp"], "180")
check("named picks it", A.from_app_recipe(multi, "large")[1][0]["values"]["tmp"], "200")
check("unknown portion falls back to first",
      A.from_app_recipe(multi, "nope")[1][0]["values"]["tmp"], "180")

print("\nmenu wrapper (the file-path form, no 599 BLE limit)")
r1 = A.to_app_recipe("Big Recipe", [("standard", [{"type": "start", "values": {"tmp": "200"}}])])
menu = A.to_menu("My Menu", [r1], category="Home Assistant")
check("menu has a description", menu["description"], "My Menu")
check("wraps recipes under a category",
      menu["recipes"][0]["name"], "Home Assistant")
check("the recipe object is inside the category",
      menu["recipes"][0]["recipes"][0]["name"], "Big Recipe")
check("category carries the app's color field", "color" in menu["recipes"][0], True)

print("\nshape detection")
check("app object recognised", A.is_app_recipe(app), True)
check("flat form is not app-schema", A.is_app_recipe({"name": "x", "steps": []}), False)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

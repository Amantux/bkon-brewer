#!/usr/bin/env python3
"""The tool set and its dispatcher.

    python3 tests/test_tools.py

Per the edibl spec: a small typed tool list and one execute_tool that never
raises -- a failing tool returns {"error": ...} the model can read, not an
exception that kills the turn.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import nl_recipe, tools, templates   # noqa: E402
from bkon_brewer.protocol import recipe as R  # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


RECIPES = {"Morning Cup": [R.start(200), R.fill(250, pause_seconds=10),
                           R.vacuum(24, 4), R.purge(50, 10)]}


print("tool schema is well-formed (what a model is handed)")
check("every tool has name/description/parameters",
      all({"name", "description", "parameters"} <= set(t) for t in tools.TOOLS), True)
check("parameters are JSON-Schema objects",
      all(t["parameters"]["type"] == "object" for t in tools.TOOLS), True)

print("\nbuild_recipe from a description")
# build_recipe now compiles the description rather than matching a keyword to a
# template, so it is asserted on what the sentence asked for, not on a key.
r = tools.execute_tool("build_recipe", {"description": "a strong bold espresso"})
check("recognises coffee", r["template"], "coffee")
check("returns steps", len(r["steps"]) >= 4, True)
check("and lints them", "problems" in r, True)
check("reports the strength it targeted",
      any(t["what"] == "strength" for t in r["targets"]), True)
r = tools.execute_tool("build_recipe", {"description": "delicate green tea"})
check("recognises delicate leaf", r["template"], "delicate tea")
r = tools.execute_tool("build_recipe", {"description": "just a coffee"})
check("defaults to coffee", r["template"], "coffee")

# the point of the compiler: numbers in the sentence reach the recipe
r = tools.execute_tool("build_recipe", {"description": "green tea at 185 F, 300 ml"})
check("the temperature target is honoured",
      any(t["value"].startswith("185") and t["honoured"] for t in r["targets"]), True)
check("a summary explains it", bool(r.get("summary")), True)
r = tools.execute_tool("build_recipe", {"description": "coffee at 400 F"})
check("an impossible target is reported, not silently accepted",
      bool(r["unmet"]), True)

print("\nlist_templates")
r = tools.execute_tool("list_templates", {})
check("lists the styles the compiler knows", len(r["styles"]), len(nl_recipe.STYLES))
check("and says how to use it", bool(r.get("example")), True)

print("\nlint_recipe over a saved recipe")
r = tools.execute_tool("lint_recipe", {"name": "Morning Cup"}, recipes=RECIPES)
check("reports ok on a good recipe", r["ok"], True)
r = tools.execute_tool("lint_recipe", {"name": "Nope"}, recipes=RECIPES)
check("unknown recipe -> error dict, not a raise", "error" in r, True)

print("\nadjust_recipe")
r = tools.execute_tool("adjust_recipe", {"name": "Morning Cup", "feedback": "stronger"},
                       recipes=RECIPES)
check("reports the change", r["changed"], True)
check("returns new steps", len(r["steps"]) >= 4, True)
check("did not mutate the stored recipe",
      int(RECIPES["Morning Cup"][2].values["ps"]), 24)

print("\ndiagnose")
r = tools.execute_tool("diagnose", {"text": "C:3 M:5"})
check("explains the code", "seal" in (r["cause"] + r["summary"]).lower(), True)

print("\nthe dispatcher never raises")
check("unknown tool -> error dict", "error" in tools.execute_tool("nope", {}), True)
check("bad args -> error dict, not a crash",
      "error" in tools.execute_tool("build_recipe", {}) or "template" in tools.execute_tool("build_recipe", {}), True)
check("lint with missing name handled",
      isinstance(tools.execute_tool("lint_recipe", {}, recipes=RECIPES), dict), True)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

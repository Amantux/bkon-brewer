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

from bkon_brewer import tools, templates   # noqa: E402
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
r = tools.execute_tool("build_recipe", {"description": "a strong bold espresso"})
check("picks the strong template", r["template"], "strong")
check("returns steps", len(r["steps"]) >= 4, True)
check("and lints them", "problems" in r, True)
r = tools.execute_tool("build_recipe", {"description": "delicate green tea"})
check("picks delicate for tea", r["template"], "delicate")
r = tools.execute_tool("build_recipe", {"description": "just a coffee"})
check("defaults to pour_over", r["template"], "pour_over")

print("\nlist_templates")
r = tools.execute_tool("list_templates", {})
check("lists all templates", len(r["templates"]), len(templates.TEMPLATES))

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

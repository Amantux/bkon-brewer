"""The tool set, in the neutral schema from the edibl chat-and-providers spec.

Per the spec (§4): a small, typed tool list `[{name, description, parameters}]`
where parameters is JSON-Schema, plus one `execute_tool` dispatcher over the
domain. Results are plain dicts, fed back to a model as text, so any provider
drives them identically -- no vendor tool-calling format leaks in here.

The tools cover the two jobs asked for: help build recipes, and debug errors or
problems. They are pure over their inputs (a recipes dict, an optional
knowledge base) so the whole tool surface is testable without a model, a brewer
or Home Assistant. A failing tool returns an `{"error": ...}` dict rather than
raising, because in an agent loop a raised exception is a dead turn and an
error dict is something the model can read and work around.
"""
from __future__ import annotations

from typing import Any, Callable

from . import advisor, diagnostics, nl_recipe, templates
from .protocol import recipe as R

# The neutral schema. Kept small and typed on purpose -- a large fuzzy tool set
# makes a model pick worse, not better.
TOOLS: list[dict] = [
    {
        "name": "list_templates",
        "description": "List the starter recipe templates a new recipe can be "
                       "built from.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "build_recipe",
        "description": "Build a starter recipe from a short description "
                       "(e.g. 'a strong bold cup' or 'delicate green tea'). "
                       "Returns the steps and any problems found.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string",
                                "description": "What kind of drink to build."}},
            "required": ["description"],
        },
    },
    {
        "name": "lint_recipe",
        "description": "Check a saved recipe for problems before brewing: "
                       "size limit, missing steps, out-of-range values.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "The saved recipe to check."}},
            "required": ["name"],
        },
    },
    {
        "name": "adjust_recipe",
        "description": "Adjust a saved recipe from feedback like 'stronger', "
                       "'less bitter', 'hotter', 'bigger'. Returns the changes "
                       "and the new steps; does not save.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "feedback": {"type": "string"}},
            "required": ["name", "feedback"],
        },
    },
    {
        "name": "diagnose",
        "description": "Explain a brewer error code (like 'C:3 M:5'), a status, "
                       "or a described symptom, with a likely cause and fix.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "The code, status, or symptom."}},
            "required": ["text"],
        },
    },
]

TOOL_NAMES = frozenset(t["name"] for t in TOOLS)


def execute_tool(name: str, arguments: dict[str, Any], *,
                 recipes: dict[str, list[R.Step]] | None = None,
                 kb=None) -> dict[str, Any]:
    """Run one tool. Never raises; a failure comes back as {"error": ...}.

    `recipes` is name -> steps (the library, resolved by the caller); `kb` is an
    optional knowledge base for symptom diagnosis. Both are injected so this
    stays pure and testable.
    """
    recipes = recipes or {}
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool {name!r}"}
    try:
        return fn(arguments, recipes, kb)
    except Exception as ex:                          # noqa: BLE001
        return {"error": f"{name} failed: {ex}"}


def _steps_out(steps: list[R.Step]) -> list[dict]:
    return [{"type": str(s.type), "values": dict(s.values)} for s in steps]


def _findings_out(findings) -> list[dict]:
    return [{"severity": f.label(), "message": f.message, "fix": f.fix,
             "step": (f.step_index + 1) if f.step_index is not None else None}
            for f in findings]


def _t_list_templates(_args, _recipes, _kb) -> dict:
    return {"templates": templates.list_templates()}


def _t_build_recipe(args, _recipes, _kb) -> dict:
    """Compile a description into steps, honouring any numbers it names."""
    desc = args.get("description", "")
    compiled = nl_recipe.compile_recipe(desc)
    findings = diagnostics.lint_recipe(compiled.steps)
    return {
        "template": compiled.style,
        "steps": _steps_out(compiled.steps),
        "problems": _findings_out(findings),
        "targets": [{"what": t.what, "value": t.value, "honoured": t.honoured}
                    for t in compiled.targets],
        "unmet": compiled.unmet,
        "summary": compiled.summary(),
        "note": "Numbers you name are honoured; the rest comes from the "
                "published base recipes. Adjust with feedback like 'stronger'.",
    }


def _t_lint_recipe(args, recipes, _kb) -> dict:
    name = args.get("name", "")
    steps = _resolve(name, recipes)
    if steps is None:
        return {"error": f"no saved recipe named {name!r}"}
    findings = diagnostics.lint_recipe(steps)
    return {
        "name": name,
        "ok": not any(f.severity == diagnostics.Severity.ERROR for f in findings),
        "problems": _findings_out(findings),
    }


def _t_adjust_recipe(args, recipes, _kb) -> dict:
    name = args.get("name", "")
    steps = _resolve(name, recipes)
    if steps is None:
        return {"error": f"no saved recipe named {name!r}"}
    result = advisor.customize(steps, args.get("feedback", ""))
    return {
        "name": name,
        "changed": result.changed,
        "summary": result.summary(),
        "steps": _steps_out(result.steps),
    }


def _t_diagnose(args, _recipes, kb) -> dict:
    d = diagnostics.diagnose(args.get("text", ""), kb=kb)
    return {"summary": d.summary, "cause": d.cause, "fix": d.fix,
            "source": d.source}


def _resolve(name: str, recipes: dict) -> list[R.Step] | None:
    if name in recipes:
        return recipes[name]
    low = name.lower().strip()
    for k, v in recipes.items():
        if k.lower() == low:
            return v
    return None


_DISPATCH: dict[str, Callable] = {
    "list_templates": _t_list_templates,
    "build_recipe": _t_build_recipe,
    "lint_recipe": _t_lint_recipe,
    "adjust_recipe": _t_adjust_recipe,
    "diagnose": _t_diagnose,
}

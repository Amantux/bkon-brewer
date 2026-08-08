"""The recipe-studio tools, over plain step dicts, backed by the vendored core.

`chat.py` runs a provider-agnostic loop that calls tools by name; this is where
those names become real work. Each tool takes ``(args, steps)`` and returns
``(result_dict, new_steps_or_None)`` — the shape the loop expects — so the build,
tune, lint and diagnose logic is exactly the code the integration ships
(``bkon_core``, vendored into the add-on and kept in sync by
``scripts/check_core_sync.py``). `answer_docs` is different: it needs the running
RAG, so `server.py` builds it as a closure and adds it to the registry.

Steps cross the wire as ``{"type": "vc", "values": {"ps": "24", ...}}`` — the
same shape the recipe builder in the webroot uses — so the chat and the builder
share one recipe state with no translation between them.
"""
from __future__ import annotations

from bkon_core import advisor, diagnostics, templates
from bkon_core.protocol import recipe as R


def _to_core(steps: list[dict]) -> list[R.Step]:
    return [R.Step(R.StepType(s["type"]), dict(s.get("values", {}))) for s in steps]


def _to_dicts(steps: list[R.Step]) -> list[dict]:
    return [{"type": str(s.type), "values": {k: str(v) for k, v in s.values.items()}}
            for s in steps]


def build_recipe(args: dict, steps: list[dict]):
    """Start a fresh recipe from a description ("a strong, small cup")."""
    key, core = templates.suggest(str(args.get("description", "")))
    new = _to_dicts(core)
    return {"template": key, "steps": len(new),
            "summary": f"Started a '{key}' recipe with {len(new)} steps."}, new


def adjust_recipe(args: dict, steps: list[dict]):
    """Tune the current recipe from plain feedback (stronger, less bitter…)."""
    result = advisor.customize(_to_core(steps), str(args.get("feedback", "")))
    changed = result.changed
    return ({"changed": changed, "summary": result.summary()},
            _to_dicts(result.steps) if changed else None)


def lint_recipe(args: dict, steps: list[dict]):
    """Check the current recipe for problems before brewing."""
    findings = diagnostics.lint_recipe(_to_core(steps))
    problems = [{"severity": f.label(), "message": f.message} for f in findings]
    errors = sum(1 for f in findings if f.severity >= diagnostics.Severity.ERROR)
    return {"ok": errors == 0, "problem_count": len(problems),
            "problems": problems}, None


def diagnose(args: dict, steps: list[dict]):
    """Explain an error code or symptom ("C:3 M:5", "it won't seal")."""
    d = diagnostics.diagnose(str(args.get("text", "")))
    return {"summary": d.summary, "cause": d.cause, "fix": d.fix}, None


#: The tools that need nothing but the vendored core — always available, because
#: building and tuning a recipe needs a model, not documents.
REGISTRY = {
    "build_recipe": build_recipe,
    "adjust_recipe": adjust_recipe,
    "lint_recipe": lint_recipe,
    "diagnose": diagnose,
}


def registry_for(answer_docs=None, score_recipe=None) -> dict:
    """The tool set for one chat turn.

    `answer_docs` is passed only when the LightRAG half of the add-on is on and
    ready; when it is off the tool is absent entirely rather than present and
    failing, so the system prompt never offers the model something it cannot
    call. `score_recipe` needs the provider, so the server injects it as a
    closure. The plain recipe tools are there either way.
    """
    tools = dict(REGISTRY)
    if answer_docs is not None:
        tools["answer_docs"] = answer_docs
    if score_recipe is not None:
        tools["score_recipe"] = score_recipe
    return tools

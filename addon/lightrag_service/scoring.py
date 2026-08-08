"""LLM recipe critique — a score, comments, and concrete suggestions.

The score itself is the model's judgement (the user chose LLM critique over a
fixed heuristic), but the model is not asked to judge in a vacuum. It is handed
the objective facts first -- the recipe rendered plainly, its wire size against
the Bluetooth budget, any envelope violations from the linter, and the confirmed
RAIN relationships -- so its verdict is grounded in what is true about the recipe
rather than in vibes. The model weighs; it does not invent the numbers.

Pure over its inputs: the provider is injected, so the whole thing is tested with
a fake provider that returns a scripted critique -- no model, no network, no
Home Assistant. Mirrors chat.py, and reuses its tolerant JSON extraction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from chat import _extract_json

# The vendored pure core (kept in sync with the integration).
from bkon_core import diagnostics
from bkon_core.protocol import recipe as R

BLE_LIMIT = 599


@dataclass(slots=True)
class Dimension:
    name: str
    rating: int          # 1-5, the model's read on this facet
    comment: str


@dataclass(slots=True)
class Critique:
    score: int                                   # 0-100 overall
    verdict: str                                 # a short phrase
    comment: str                                 # 2-3 sentences
    dimensions: list[Dimension] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)    # the objective inputs, for transparency


# The confirmed design relationships, handed to the model as grounding. Facts,
# not opinions -- from docs/INTEL.md and the RAIN development guide.
_GROUNDING = """Grounding facts (from BKON/Franke's own documentation — treat as true):
- The vacuum is the machine's signature. It sets concentration; steep time sets
  flavour intensity. A recipe with no real vacuum is barely using the machine.
- Base tea recipes: low-temp starts 175 F / 24 kPa, high-temp 205 F / 20 kPa —
  a hotter brew starts from a SHALLOWER vacuum, not a deeper one.
- In a multi-vacuum sequence, if the first is X kPa the next is about X+2 and the
  third about X+1. Delicate teas use ONE vacuum, a short steep, water front-loaded.
- The app accepts: temperature 140-212 F, vacuum 0-60 kPa, purge pressure 25-35,
  fill/rinse 0-600 ml, every time 0-180 s. Values outside these will not brew.
- A recipe must fit 599 bytes to brew over Bluetooth; larger needs a USB menu file."""

SYSTEM = """You are a BKON coffee-brewer recipe judge. You score a recipe out of 100
and explain the score in plain, practical language a barista would use. Be
specific to THIS recipe — name the vacuum, the steep, the temperature. Reward
recipes that use the vacuum meaningfully and sit inside the accepted ranges;
mark down ones that waste the machine, break the ranges, or will not fit
Bluetooth. Do not invent numbers you were not given.

Reply with ONLY a JSON object:
{"score": <0-100 int>,
 "verdict": "<up to 6 words>",
 "comment": "<2-3 sentences>",
 "dimensions": [{"name": "Extraction", "rating": <1-5>, "comment": "<one line>"}, ...],
 "suggestions": ["<a concrete change>", "..."]}
Use 3-5 dimensions such as Extraction, Balance, Structure, Validity, Fit."""


def _render(steps: list[dict]) -> str:
    if not steps:
        return "The recipe is empty."
    lines = []
    for i, s in enumerate(steps, 1):
        vals = ", ".join(f"{k}={v}" for k, v in s.get("values", {}).items())
        lines.append(f"  {i}. {s.get('type')} ({vals})")
    return "\n".join(lines)


def facts_for(steps: list[dict]) -> dict:
    """The objective inputs, computed deterministically, handed to the model."""
    core = [R.Step(R.StepType(s["type"]), dict(s.get("values", {}))) for s in steps]
    size = len(R.encode(core)) if core else 0
    findings = diagnostics.lint_recipe(core) if core else []
    problems = [f"{f.label()}: {f.message}" for f in findings]
    return {
        "step_count": len(steps),
        "bytes": size,
        "ble_limit": BLE_LIMIT,
        "fits_bluetooth": size <= BLE_LIMIT,
        "problems": problems,
    }


def _prompt(steps: list[dict], facts: dict) -> str:
    problems = "\n".join(f"  - {p}" for p in facts["problems"]) or "  (none found)"
    return (
        f"{_GROUNDING}\n\n"
        f"Recipe:\n{_render(steps)}\n\n"
        f"Objective facts about it:\n"
        f"  - {facts['step_count']} steps, {facts['bytes']} of {facts['ble_limit']} "
        f"bytes ({'fits' if facts['fits_bluetooth'] else 'TOO LARGE for'} Bluetooth)\n"
        f"  - linter says:\n{problems}\n\n"
        f"Score this recipe. Respond with the JSON object only."
    )


def _coerce(obj: dict, facts: dict) -> Critique:
    def _int(v, lo, hi, default):
        try:
            return max(lo, min(hi, int(round(float(v)))))
        except (TypeError, ValueError):
            return default

    dims = []
    for d in obj.get("dimensions") or []:
        if isinstance(d, dict) and d.get("name"):
            dims.append(Dimension(
                name=str(d["name"])[:40],
                rating=_int(d.get("rating"), 1, 5, 3),
                comment=str(d.get("comment", "")).strip()))
    suggestions = [str(s).strip() for s in (obj.get("suggestions") or []) if str(s).strip()]
    return Critique(
        score=_int(obj.get("score"), 0, 100, 50),
        verdict=str(obj.get("verdict", "")).strip()[:60] or "Scored",
        comment=str(obj.get("comment", "")).strip(),
        dimensions=dims[:6],
        suggestions=suggestions[:5],
        facts=facts,
    )


async def score_recipe(provider, steps: list[dict]) -> Critique:
    """Score one recipe. `provider` needs only `complete(prompt, system=...)`."""
    steps = list(steps or [])
    facts = facts_for(steps)
    raw = await provider.complete(_prompt(steps, facts), system=SYSTEM)
    obj = _extract_json(raw)
    if obj is None:
        # The model answered in prose. Keep its words rather than throwing them
        # away; the facts still stand on their own.
        return Critique(score=50, verdict="Unscored",
                        comment=raw.strip()[:600], facts=facts)
    return _coerce(obj, facts)

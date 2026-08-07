"""Feedback-driven recipe customisation. Pure; see docs/INTEL.md for grounding.

Turns plain-language feedback -- "make it stronger", "less bitter", "a bit
cooler" -- into concrete parameter changes on a recipe, and explains each change
in terms a person asked for rather than the wire keys.

The adjustments are not invented. They follow the relationships stated in
BKON/Franke's RAIN Menu Development Guide: extraction strength is driven by
vacuum depth (kPa) and steep time (seconds), and temperature governs how much
is pulled from the grounds. So "stronger" deepens the vacuum and lengthens the
steep; "less bitter" eases the temperature and shortens the steep. Every change
is bounded to the documented operating ranges, and nothing here guesses beyond
what the guide supports -- an adjustment it cannot ground, it declines to make.

Pure by design: no I/O, no Home Assistant. The judgement about what "stronger"
does to a recipe is the part most worth testing, and testing it means it can be
trusted before it ever changes a real brew.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .protocol import recipe as R

# Documented operating envelope (docs/INTEL.md). Adjustments clamp to these so a
# stack of "stronger, stronger, stronger" cannot walk a value somewhere the
# machine will reject or, worse, silently misread.
TEMP_MIN, TEMP_MAX = 165, 210          # deg F, usable range from the RAIN guide
VAC_MIN, VAC_MAX = 1, 101              # kPa; 101 ~ full vacuum
TIME_MIN = 0
FILL_MIN = 5                            # ml; a fill of zero is not a fill


@dataclass(slots=True)
class Change:
    """One human-readable change, for the explanation."""

    what: str
    detail: str


@dataclass(slots=True)
class Customisation:
    steps: list[R.Step]
    changes: list[Change] = field(default_factory=list)
    #: Intents we recognised but could not act on (e.g. no step to change).
    unmet: list[str] = field(default_factory=list)
    #: True if we understood no intent at all.
    not_understood: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.changes)

    def summary(self) -> str:
        if self.not_understood:
            return ("I could not tell what to change. Try words like stronger, "
                    "weaker, hotter, cooler, less bitter, bigger or faster.")
        if not self.changes:
            return ("Nothing to change for that — " + "; ".join(self.unmet)
                    if self.unmet else "Nothing to change.")
        lines = [f"- {c.what}: {c.detail}" for c in self.changes]
        if self.unmet:
            lines.append("(Could not: " + "; ".join(self.unmet) + ")")
        return "\n".join(lines)


# -- intent vocabulary -------------------------------------------------------
# Each intent maps synonyms a person actually uses onto a direction. Matching is
# word-boundary based so "cooler" does not trip "cool" inside another word.

_INTENTS: dict[str, list[str]] = {
    "stronger": ["stronger", "bolder", "more intense", "more intensity",
                 "richer", "more concentrated", "punchier", "robust"],
    "weaker": ["weaker", "lighter", "milder", "less intense", "less strong",
               "more delicate", "subtle"],
    "hotter": ["hotter", "warmer", "more heat", "higher temp", "hot"],
    "cooler": ["cooler", "colder", "less heat", "lower temp", "cool"],
    "less_bitter": ["less bitter", "smoother", "less harsh", "sweeter",
                    "not so bitter", "too bitter"],
    "more_bitter": ["more bitter", "sharper", "more bite", "more edge"],
    "faster": ["faster", "quicker", "shorter", "speed it up", "less time"],
    "slower": ["slower", "longer", "more time", "extend"],
    "bigger": ["bigger", "larger", "more water", "larger cup", "fuller"],
    "smaller": ["smaller", "less water", "smaller cup"],
}


def parse_feedback(text: str) -> list[str]:
    """Which intents a piece of feedback expresses. Order-stable, de-duplicated.

    A single sentence can carry several ("stronger and a touch cooler"), so this
    returns all matches rather than a single best guess.
    """
    low = f" {text.lower()} "
    found: list[str] = []
    for intent, phrases in _INTENTS.items():
        for p in phrases:
            if re.search(rf"(?<![a-z]){re.escape(p)}(?![a-z])", low):
                found.append(intent)
                break
    return found


# -- the transforms ----------------------------------------------------------

def customize(steps: list[R.Step], feedback: str) -> Customisation:
    """Apply the feedback to a copy of the recipe. The original is untouched."""
    intents = parse_feedback(feedback)
    if not intents:
        return Customisation(_clone(steps), not_understood=True)

    work = _clone(steps)
    changes: list[Change] = []
    unmet: list[str] = []

    for intent in intents:
        handler = _HANDLERS[intent]
        handler(work, changes, unmet)

    return Customisation(work, changes, unmet)


def _clone(steps: list[R.Step]) -> list[R.Step]:
    return [R.Step(s.type, dict(s.values)) for s in steps]


def _vac_steps(steps):
    return [s for s in steps if s.type == R.StepType.VACUUM]


def _fill_steps(steps):
    return [s for s in steps if s.type == R.StepType.FILL]


def _start_step(steps):
    for s in steps:
        if s.type == R.StepType.START:
            return s
    return None


def _adjust_vacuum(steps, delta_kpa, changes, label):
    vacs = _vac_steps(steps)
    if not vacs:
        return False
    for s in vacs:
        cur = int(float(s.values.get("ps", 0)))
        s.values["ps"] = max(VAC_MIN, min(VAC_MAX, cur + delta_kpa))
    verb = "Deepened" if delta_kpa > 0 else "Eased"
    changes.append(Change(
        label, f"{verb} the vacuum by {abs(delta_kpa)} kPa across "
               f"{len(vacs)} vacuum step{'s' if len(vacs) != 1 else ''}"))
    return True


def _adjust_steep(steps, delta_s, changes, label):
    """Steep time lives in two places: the fill's atmospheric pause (dl) and the
    vacuum hold (tm). Both are 'steep' in the guide's sense, so both move."""
    touched = 0
    for s in _fill_steps(steps):
        cur = int(float(s.values.get("dl", 0)))
        s.values["dl"] = max(TIME_MIN, cur + delta_s)
        touched += 1
    for s in _vac_steps(steps):
        cur = int(float(s.values.get("tm", 0)))
        new = max(1, cur + delta_s)          # a vacuum of 0s is not a vacuum
        s.values["tm"] = new
        touched += 1
    if not touched:
        return False
    verb = "Lengthened" if delta_s > 0 else "Shortened"
    changes.append(Change(label, f"{verb} steep time by {abs(delta_s)}s"))
    return True


def _adjust_temp(steps, delta_f, changes, label):
    st = _start_step(steps)
    if st is None:
        return False
    cur = int(float(st.values.get("tmp", 205)))
    new = max(TEMP_MIN, min(TEMP_MAX, cur + delta_f))
    st.values["tmp"] = new
    if new == cur:
        return False
    changes.append(Change(label, f"Set temperature to {new} °F (was {cur})"))
    return True


def _adjust_fill(steps, delta_ml, changes, label):
    fills = _fill_steps(steps)
    if not fills:
        return False
    for s in fills:
        cur = int(float(s.values.get("fwv", 0)))
        s.values["fwv"] = max(FILL_MIN, cur + delta_ml)
    verb = "Increased" if delta_ml > 0 else "Reduced"
    changes.append(Change(label, f"{verb} fill volume by {abs(delta_ml)} ml"))
    return True


# Each handler tries its changes and records either a Change or an "unmet"
# reason, so the explanation can say *why* nothing happened ("no vacuum step to
# deepen") rather than silently doing part of the ask.

def _h_stronger(steps, changes, unmet):
    a = _adjust_vacuum(steps, +2, changes, "Stronger")
    b = _adjust_steep(steps, +5, changes, "Stronger")
    if not (a or b):
        unmet.append("stronger needs a vacuum or fill step to work on")

def _h_weaker(steps, changes, unmet):
    a = _adjust_vacuum(steps, -2, changes, "Lighter")
    b = _adjust_steep(steps, -5, changes, "Lighter")
    if not (a or b):
        unmet.append("lighter needs a vacuum or fill step to work on")

def _h_hotter(steps, changes, unmet):
    if not _adjust_temp(steps, +5, changes, "Hotter"):
        unmet.append("already at the maximum safe temperature, or no start step")

def _h_cooler(steps, changes, unmet):
    if not _adjust_temp(steps, -5, changes, "Cooler"):
        unmet.append("already at the minimum temperature, or no start step")

def _h_less_bitter(steps, changes, unmet):
    a = _adjust_temp(steps, -5, changes, "Less bitter")
    b = _adjust_steep(steps, -5, changes, "Less bitter")
    if not (a or b):
        unmet.append("less bitter needs a start or steep step to ease")

def _h_more_bitter(steps, changes, unmet):
    a = _adjust_temp(steps, +5, changes, "More bitter")
    b = _adjust_steep(steps, +5, changes, "More bitter")
    if not (a or b):
        unmet.append("more bitter needs a start or steep step")

def _h_faster(steps, changes, unmet):
    if not _adjust_steep(steps, -5, changes, "Faster"):
        unmet.append("nothing with a steep time to shorten")

def _h_slower(steps, changes, unmet):
    if not _adjust_steep(steps, +5, changes, "Slower"):
        unmet.append("nothing with a steep time to lengthen")

def _h_bigger(steps, changes, unmet):
    if not _adjust_fill(steps, +25, changes, "Bigger"):
        unmet.append("no fill step whose volume to raise")

def _h_smaller(steps, changes, unmet):
    if not _adjust_fill(steps, -25, changes, "Smaller"):
        unmet.append("no fill step whose volume to lower")


_HANDLERS = {
    "stronger": _h_stronger, "weaker": _h_weaker,
    "hotter": _h_hotter, "cooler": _h_cooler,
    "less_bitter": _h_less_bitter, "more_bitter": _h_more_bitter,
    "faster": _h_faster, "slower": _h_slower,
    "bigger": _h_bigger, "smaller": _h_smaller,
}

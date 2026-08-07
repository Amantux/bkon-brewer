"""Recipe linting and problem diagnosis. Pure; see docs/INTEL.md for the ranges.

Two jobs, both about catching trouble before it costs a brew:

  lint_recipe  -- inspect a recipe for problems, from "won't transmit" down to
                  "this looks unusual", each with a plain-language fix.
  diagnose     -- turn an error code, a status, or a described symptom into a
                  likely cause and a next step, grounded in the service docs.

Every check is grounded: the ranges come from BKON/Franke's RAIN guide and the
error labels from their Error Codes reference. A lint finding is only raised
when it is defensible from that material -- guessing would train the user to
ignore the warnings, which is worse than staying quiet.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .protocol import recipe as R
from .protocol.events import ERROR_MESSAGES

# Confirmed operating envelope (docs/INTEL.md). Used for range checks; a value
# outside these is worth flagging, not silently clamping -- the person built it
# on purpose and deserves to know it looks wrong.
TEMP_MIN, TEMP_MAX = 165, 210          # deg F
VAC_TYPICAL_MAX = 101                  # kPa; ~full vacuum
TIME_MAX_S = 180                       # the app validates times under 3 minutes


class Severity(IntEnum):
    ERROR = 3        # will not brew, or will brew something other than intended
    WARNING = 2      # suspect; probably not what you meant
    INFO = 1         # worth knowing, not a problem


@dataclass(slots=True)
class Finding:
    severity: Severity
    message: str
    fix: str
    step_index: int | None = None      # which step, when it is step-specific

    def label(self) -> str:
        return {Severity.ERROR: "error", Severity.WARNING: "warning",
                Severity.INFO: "info"}[self.severity]


def lint_recipe(steps: list[R.Step]) -> list[Finding]:
    """Every problem in a recipe, most severe first.

    Ordered by severity so the first line is the one that matters most. An empty
    list means the recipe is sound as far as the documented rules can tell --
    which is not the same as "will taste good", and the info notes say so.
    """
    findings: list[Finding] = []

    if not steps:
        return [Finding(Severity.ERROR, "The recipe has no steps.",
                        "Add at least a Start and a Fill before brewing.")]

    # -- structural: will it even make sense as a brew? -------------------
    types = [s.type for s in steps]
    if R.StepType.START not in types:
        findings.append(Finding(
            Severity.WARNING,
            "No Start step, so the water temperature is not set.",
            "Add a Start step with your target temperature; without it the "
            "machine uses whatever it was last at."))
    has_water = any(t in (R.StepType.FILL,) for t in types)
    if not has_water:
        findings.append(Finding(
            Severity.ERROR,
            "No Fill step, so no water is added — nothing will brew.",
            "Add a Fill step with a volume in millilitres."))
    if R.StepType.VACUUM not in types:
        findings.append(Finding(
            Severity.INFO,
            "No Vacuum step. Vacuum extraction is what this machine does "
            "differently; a recipe without one is just steeping.",
            "Add a Vacuum step if you want the machine's signature extraction."))

    # -- the hard limit: will it transmit? --------------------------------
    try:
        payload = R.encode(steps)
        size = len(payload.encode("utf-8"))
        if size > R.MAX_RECIPE_BYTES:
            findings.append(Finding(
                Severity.ERROR,
                f"Too large to send over Bluetooth: {size} of "
                f"{R.MAX_RECIPE_BYTES} bytes.",
                "Combine adjacent steps — merging two purges, or dropping a "
                "rinse you do not need, is usually enough."))
        elif size > R.MAX_RECIPE_BYTES * 0.9:
            findings.append(Finding(
                Severity.WARNING,
                f"Close to the Bluetooth size limit ({size} of "
                f"{R.MAX_RECIPE_BYTES} bytes).",
                "It will send, but adding much more will not. Consider trimming."))
    except Exception as ex:                          # noqa: BLE001
        findings.append(Finding(
            Severity.ERROR, f"The recipe could not be encoded: {ex}",
            "Check each step's values are numbers where numbers are expected."))

    # -- per-step: values that look wrong ---------------------------------
    for i, s in enumerate(steps):
        findings.extend(_lint_step(i, s))

    findings.sort(key=lambda f: (-f.severity, f.step_index or 0))
    return findings


def _lint_step(i: int, s: R.Step) -> list[Finding]:
    out: list[Finding] = []
    v = s.values

    if s.type == R.StepType.START:
        tmp = _num(v.get("tmp"))
        if tmp is None:
            out.append(Finding(Severity.ERROR, f"Step {i + 1} (Start) has no "
                        "temperature.", "Set a temperature in °F.", i))
        elif not (TEMP_MIN <= tmp <= TEMP_MAX):
            out.append(Finding(
                Severity.WARNING,
                f"Step {i + 1} temperature {tmp:g} °F is outside the documented "
                f"{TEMP_MIN}–{TEMP_MAX} °F range.",
                f"Set it between {TEMP_MIN} and {TEMP_MAX} °F unless you know the "
                f"machine accepts more.", i))

    if s.type == R.StepType.FILL:
        fwv = _num(v.get("fwv"))
        if not fwv:
            out.append(Finding(
                Severity.ERROR,
                f"Step {i + 1} (Fill) has no fill volume, so it adds no water.",
                "Set a fill volume in millilitres.", i))

    if s.type == R.StepType.VACUUM:
        if not _num(v.get("tm")):
            out.append(Finding(
                Severity.WARNING,
                f"Step {i + 1} (Vacuum) has no hold time, so the vacuum does "
                "nothing.", "Set a hold time in seconds (base recipes use a "
                "few seconds).", i))
        ps = _num(v.get("ps"))
        if ps is not None and ps > VAC_TYPICAL_MAX:
            out.append(Finding(
                Severity.WARNING,
                f"Step {i + 1} vacuum {ps:g} kPa exceeds full vacuum "
                f"(~{VAC_TYPICAL_MAX} kPa).",
                "Lower it; base recipes sit around 20–24 kPa.", i))

    if s.type == R.StepType.PURGE:
        if not _num(v.get("ps")):
            out.append(Finding(
                Severity.WARNING,
                f"Step {i + 1} (Purge) has no pressure set.",
                "Set a purge pressure, or remove the step if not needed.", i))

    if s.type == R.StepType.DIALOG:
        if not str(v.get("text") or "").strip():
            out.append(Finding(
                Severity.ERROR,
                f"Step {i + 1} (Dialog) has no text, so it pauses with a blank "
                "prompt.", "Add the message to show the operator.", i))

    # A time longer than the app allows anywhere.
    for key in ("tm", "dl"):
        t = _num(v.get(key))
        if t is not None and t > TIME_MAX_S:
            out.append(Finding(
                Severity.WARNING,
                f"Step {i + 1} has a {t:g}s time, over the ~3 minute limit the "
                "app enforces.",
                "Shorten it to under 180 seconds.", i))
    return out


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- diagnosis ---------------------------------------------------------------

@dataclass(slots=True)
class Diagnosis:
    summary: str
    cause: str
    fix: str
    source: str | None = None


def diagnose(text: str, kb=None) -> Diagnosis:
    """Explain an error code, a status, or a described symptom.

    Tries three readings in order of certainty: an explicit `C:x M:y` code
    (looked up in the confirmed table), a known brewer status word, then a
    free-text symptom (handed to the knowledge base if one is available). The
    fall-through to the docs means a symptom we have not hard-coded still gets a
    real answer instead of a shrug.
    """
    import re
    m = re.search(r"C\s*:?\s*(\d+)\s*M\s*:?\s*(\d+)", text, re.IGNORECASE)
    if m:
        key = f"{m.group(2)}:{m.group(1)}"
        desc = ERROR_MESSAGES.get(key)
        if desc:
            return Diagnosis(
                summary=f"Error C:{m.group(1)} M:{m.group(2)}",
                cause=desc,
                fix=_fix_hint(key),
                source="BKON error codes")
        return Diagnosis(
            summary=f"Error C:{m.group(1)} M:{m.group(2)}",
            cause="An error the documented table does not cover.",
            fix="Restart the machine; if it recurs, note what it was doing and "
                "check the service documentation for this code.",
            source=None)

    low = text.lower()
    for word, diag in _STATUS_DIAGNOSES.items():
        if word in low:
            return diag

    if kb is not None and getattr(kb, "ready", False):
        answer = kb.answer(text)
        return Diagnosis(
            summary="From the BKON documents",
            cause=answer,
            fix="Follow the step above; if it does not resolve, restart and "
                "retry before calling service.",
            source="knowledge base")

    return Diagnosis(
        summary="Not enough to go on",
        cause="I could not match that to a known error, status, or document.",
        fix="Quote the exact code shown (like C:3 M:5), or describe what the "
            "machine is doing, and I will look again.")


def _fix_hint(key: str) -> str:
    hints = {
        "2:45": "Empty and rinse the pitcher; the descale cycle is done.",
        "5:1": "Reseat the brew chamber glass and make sure it is fully in.",
        "5:3": "Close and seat the chamber; a vacuum cannot form if it is not "
               "sealed. Check the purge valve if it persists.",
        "5:40": "Check the water supply is connected and the inlet is open.",
        "5:50": "A module lost contact — restart the machine; if it recurs it is "
                "a service call.",
    }
    if key.startswith("5:1") or key in ("5:11", "5:12", "5:13", "5:16",
                                        "5:17", "5:18", "5:19", "5:22"):
        return ("A temperature sensor fault. Restart once; if it returns it "
                "usually needs service rather than anything you can adjust.")
    return hints.get(key, "Restart the machine and retry; if it recurs, check "
                          "the service documentation for this code.")


_STATUS_DIAGNOSES = {
    "not sealed": Diagnosis(
        "Chamber not sealed",
        "The brew chamber is not closed or seated, so a vacuum cannot form.",
        "Open and reseat the chamber, then close it firmly. If it still reports "
        "unsealed, inspect the purge valve.",
        "BKON error codes"),
    "descale": Diagnosis(
        "Descaling",
        "The machine is running or has finished a descale cycle.",
        "When it reports finished, empty and rinse the pitcher before brewing.",
        "BKON maintenance"),
    "no water": Diagnosis(
        "No water / flow fault",
        "The machine is not getting water — supply off, or a flow-meter fault.",
        "Check the water supply is connected and the shut-off valve is open.",
        "BKON error codes"),
}

"""Recipe model and wire encoding. See docs/PROTOCOL.md.

Pure: no I/O, no Bluetooth, no Home Assistant. The encoding rules recovered from
the vendor app are subtle and several of them are invisible when wrong — a
recipe that encodes "nearly right" still brews, just not the drink you asked
for. Keeping this layer pure means those rules can be tested against known-good
output rather than discovered by drinking the results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import quote

#: Hard ceiling from the vendor app, which refuses to transmit anything longer.
#: Treated as a validation rule rather than a runtime error: finding out a
#: recipe is untransmittable at brew time is finding out too late.
MAX_RECIPE_BYTES = 599

#: Keys whose zero value is dropped rather than sent. Absent and zero are not
#: the same thing to the firmware, and sending "0" where the app sends nothing
#: is the single easiest way to produce a recipe that behaves differently from
#: the same recipe in the app.
_DROP_IF_ZERO = frozenset({"fwv", "rwv", "ap", "ps", "tm", "dl"})


class StepType(StrEnum):
    """Step codes as they appear on the wire."""

    START = "start"      # heat to temperature
    FILL = "fr"          # fill + rinse volumes, and a pause
    VACUUM = "vc"        # the vacuum extraction this machine exists for
    PURGE = "pg"         # pressure, hold, detect
    DIALOG = "dialog"    # stop and ask the operator something
    BREW_OUT = "bo"      # dispense; appended automatically when absent


#: Only these are user-addable in the vendor app. START and BREW_OUT are
#: structural and are managed for you.
ADDABLE = (StepType.FILL, StepType.VACUUM, StepType.PURGE, StepType.DIALOG)


@dataclass(slots=True)
class Step:
    """One step. `values` are kept as given and normalised at encode time."""

    type: StepType
    values: dict[str, Any] = field(default_factory=dict)

    def normalised(self) -> dict[str, str]:
        """Apply the vendor app's value rules. See docs/PROTOCOL.md.

        Two rules, both load-bearing:
        zero-valued size keys are removed entirely, and everything that survives
        is stringified — the app sends `"205"`, never `205`.
        """
        out: dict[str, str] = {}
        for key, value in self.values.items():
            key = key.lower()
            if key in _DROP_IF_ZERO and _is_zero(value):
                continue
            out[key] = str(value)
        return out


def _is_zero(value: Any) -> bool:
    try:
        return int(float(value)) == 0
    except (TypeError, ValueError):
        return False


# -- step constructors -------------------------------------------------------
# Thin, but they exist so callers name parameters rather than remembering that
# rinse volume is "rwv". Every one of these keys is a two-or-three letter
# abbreviation that is easy to transpose and impossible to notice transposed.

def start(temperature_f: float) -> Step:
    """Heat to a temperature, in degrees Fahrenheit.

    Units confirmed from BKON/Franke's RAIN development guide: water is
    delivered to +/-1 degF, over a usable range of roughly 165-210 degF. The
    app rebuilds this step from scratch keeping only a rounded temperature and
    discarding everything else, so we construct it the same way rather than
    passing other values through and hoping the firmware ignores them.
    """
    return Step(StepType.START, {"tmp": str(round(temperature_f))})


def fill(fill_volume_ml: int, rinse_volume_ml: int = 0,
         pause_seconds: int = 0) -> Step:
    """Fill and rinse volumes in millilitres; atmospheric pause in seconds.

    Confirmed from the app's menu data and the RAIN guide: fill and rinse are in
    ml, and a fill's steep pause is the `ap` (atmospheric pause) key -- NOT `dl`,
    which is the purge delay. Getting this wrong stores the pause where the
    firmware does not read it, and the steep silently does nothing.
    """
    return Step(StepType.FILL, {"fwv": fill_volume_ml, "rwv": rinse_volume_ml,
                                "ap": pause_seconds})


def vacuum(strength_kpa: int, time_seconds: int) -> Step:
    """Vacuum strength in kilopascals; duration in seconds.

    The vacuum is the heart of the machine. Confirmed from the RAIN guide:
    strength is measured in kPa (base recipes sit around 20-24 kPa) and the
    vacuum is typically held for only a few seconds.
    """
    return Step(StepType.VACUUM, {"ps": strength_kpa, "tm": time_seconds})


def purge(pressure: int, time_seconds: int, delay_seconds: int = 0,
          detect: bool = False, manual_stop: bool = False) -> Step:
    """A purge.

    `manual_stop` is deliberately not a wire value. The firmware has no such
    concept — the vendor app fakes it by attaching a dialog telling the operator
    to stop it themselves, and drops the flag. Replicated in `encode` so the
    behaviour matches rather than silently doing nothing.
    """
    values: dict[str, Any] = {"ps": pressure, "tm": time_seconds,
                              "det": int(detect)}
    if delay_seconds:
        values["dl"] = delay_seconds
    if manual_stop:
        values["manstop"] = 1
    return Step(StepType.PURGE, values)


def dialog(text: str) -> Step:
    return Step(StepType.DIALOG, {"text": text})


def brew_out(brew_time: int = 4) -> Step:
    return Step(StepType.BREW_OUT, {"bt": brew_time})


# -- encoding ----------------------------------------------------------------

MANUAL_STOP_DIALOG = (
    "Manually stop the purge or it will close when it's finished")


def prepare(steps: list[Step]) -> list[dict[str, Any]]:
    """Apply every serialisation rule and return wire-ready step dicts.

    This is a faithful re-implementation of the vendor app's `prepRecipe`,
    including the parts that look like bugs. Deviating "sensibly" here would
    mean our recipes and the app's recipes brew differently from identical
    inputs, and that difference would only ever show up in the cup.
    """
    out: list[dict[str, Any]] = []
    has_brew_out = any(s.type == StepType.BREW_OUT for s in steps)

    for step in steps:
        values = step.normalised()

        if step.type == StepType.PURGE and values.get("manstop") == "1":
            # Rebuilt, not edited: the app emits only these keys and drops the
            # rest, so carrying extras through would not match.
            rebuilt: dict[str, str] = {"dialog": MANUAL_STOP_DIALOG}
            if "det" in values:
                rebuilt["det"] = values["det"]
            if values.get("ps"):
                rebuilt["ps"] = values["ps"]
            if values.get("tm"):
                rebuilt["tm"] = values["tm"]
            out.append({"type": str(StepType.PURGE), "values": rebuilt})
            continue

        if step.type == StepType.PURGE:
            values.pop("manstop", None)

        if step.type == StepType.START:
            values = {"tmp": str(round(float(values.get("tmp", 0))))}

        if step.type == StepType.DIALOG and "text" in values:
            # The app URL-encodes and then escapes the apostrophe separately,
            # because quote() leaves it alone by default and an unescaped
            # apostrophe breaks the app's own single-quoted bridge call.
            values["text"] = quote(values["text"], safe="").replace("'", "%27")

        out.append({"type": str(step.type), "values": values})

    if not has_brew_out:
        out.append({"type": str(StepType.BREW_OUT), "values": {"bt": "4"}})
    return out


def encode(steps: list[Step]) -> str:
    """The JSON payload handed to the transport."""
    return json.dumps(prepare(steps), separators=(",", ":"))


def encode_xml(step: dict[str, Any]) -> str:
    """One step as the tag form the brewer actually receives.

    `{"type": "pg", "values": {"ps": "50"}}` becomes `<PG><PS>50</PS></PG>`.
    Used for direct commands, and to make tests assert against something
    readable rather than a JSON blob.
    """
    tag = step["type"].upper()
    body = "".join(f"<{k.upper()}>{v}</{k.upper()}>"
                   for k, v in step["values"].items())
    return f"<{tag}>{body}</{tag}>"


def encode_command(step: Step) -> str:
    """A single step as a direct command, e.g. a manual purge."""
    return encode_xml(prepare([step])[0])


def frame(payload: str, kind: int = 1) -> str:
    """Wrap a payload in the transport frame: `{msg:1:<PG>…</PG>}`."""
    return f"{{msg:{kind}:{payload}}}"


ABORT = frame("<ABORT></ABORT>")
CANCEL = frame("<CANCEL></CANCEL>")


# -- validation --------------------------------------------------------------

class RecipeTooLarge(ValueError):
    """Over the transmittable size. Raised at build time, not at brew time."""


def validate(steps: list[Step]) -> str:
    """Encode, checking the size limit. Returns the payload."""
    payload = encode(steps)
    size = len(payload.encode("utf-8"))
    if size > MAX_RECIPE_BYTES:
        raise RecipeTooLarge(
            f"Recipe encodes to {size} bytes; the brewer accepts at most "
            f"{MAX_RECIPE_BYTES}. Consolidate steps — combining adjacent "
            f"purges is usually the easiest saving.")
    return payload

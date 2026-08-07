"""Parsing the brewer -> host direction. See docs/PROTOCOL.md.

Pure: strings in, structured events out, no I/O. The brewer speaks to us in
`event:payload` lines pushed up the notify characteristic, and this turns them
into something an integration can act on.

The error descriptions here are paraphrased from the vendor app's own code
table, not copied — enough to tell the user what to do, keyed by the same
`(C:code M:module)` identifiers the firmware reports, with the raw identifier
preserved so an unmapped code is still legible rather than swallowed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import unquote


class EventType(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    STEP_COMPLETED = "step_completed"
    RECIPE_COMPLETED = "recipe_completed"
    DIALOG = "dialog"
    DEVICE_FOUND = "device_found"
    NOTIFY = "notify"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class BrewerEvent:
    type: EventType
    #: Human-readable text where the event carries any (dialog, notify, error).
    text: str = ""
    #: Original payload, so nothing is lost when we do not recognise a shape.
    raw: str = ""
    #: For errors: the "C:code M:module" identifier, kept even when unmapped.
    code: str | None = None


# Map the app's `event:` prefixes onto our vocabulary. is_connected carries a
# 0/1 the app splits on, so it is handled specially below.
_PREFIX = {
    "stepCompleted": EventType.STEP_COMPLETED,
    "recipeCompleted": EventType.RECIPE_COMPLETED,
    "dialog": EventType.DIALOG,
    "new_device": EventType.DEVICE_FOUND,
    "notify": EventType.NOTIFY,
}

# An error code as it appears in text: "(C:45 M:2)".
_CODE_RE = re.compile(r"\(\s*C\s*:\s*(\d+)\s*M\s*:\s*(\d+)\s*\)", re.IGNORECASE)


def parse_event(line: str) -> BrewerEvent:
    """Turn one bridge line into a BrewerEvent.

    Unrecognised input becomes UNKNOWN with the raw text intact, never an
    exception — a firmware that adds a new message must not crash the
    integration, only be unhandled.
    """
    if not line:
        return BrewerEvent(EventType.UNKNOWN, raw=line)

    prefix, _, payload = line.partition(":")
    prefix = prefix.strip()

    if prefix == "is_connected":
        return BrewerEvent(
            EventType.CONNECTED if payload.strip() == "1"
            else EventType.DISCONNECTED, raw=line)

    # Bare events with no payload.
    if line.strip() in ("recipeCompleted", "stepCompleted"):
        return BrewerEvent(_PREFIX[line.strip()], raw=line)

    kind = _PREFIX.get(prefix)
    if kind is None:
        # Some payloads are themselves an error line without a prefix.
        if _CODE_RE.search(line):
            return _as_error(line)
        return BrewerEvent(EventType.UNKNOWN, raw=line)

    text = payload
    if kind == EventType.DIALOG:
        # Dialog text was URL-encoded on the way down; decode for display.
        text = unquote(payload)

    # A notify that carries an error identifier is really an error.
    if kind == EventType.NOTIFY and _CODE_RE.search(payload):
        return _as_error(payload)

    return BrewerEvent(kind, text=text.strip(), raw=line)


def _as_error(text: str) -> BrewerEvent:
    m = _CODE_RE.search(text)
    code = None
    friendly = text.strip()
    if m:
        code = f"C:{m.group(1)} M:{m.group(2)}"
        key = f"{m.group(2)}:{m.group(1)}"          # module:code
        friendly = ERROR_MESSAGES.get(key, text.strip())
    return BrewerEvent(EventType.ERROR, text=friendly, raw=text, code=code)


def describe_error(module: int | str, code: int | str) -> str:
    """Look up a paraphrased message for a (module, code) pair.

    Falls back to the bare identifier so an unmapped code is still reported as
    something rather than silently dropped.
    """
    key = f"{module}:{code}"
    return ERROR_MESSAGES.get(key, f"Brewer error C:{code} M:{module}")


# Paraphrased from the vendor app's error table. Only the actionable meaning is
# kept; the raw identifier is always available alongside via BrewerEvent.code.
# Anything not listed degrades to "Brewer error C:x M:y", which is still useful.
ERROR_MESSAGES: dict[str, str] = {
    # module 2 - brew data
    "2:20": "Brew information incomplete or missing. Restart the machine and "
            "pick a different brew; if it persists, re-send the recipe.",
    "2:30": "Incorrect brew data. Restart the machine and pick a different "
            "brew; if it persists, re-send the recipe.",
    "2:45": "Descale finished. Empty and clean the pitcher.",
    # module 4
    "4:4": "Machine reported a fault. Restart and try again.",
    "4:70": "Machine communication error.",
    # module 5 - largely hardware/sensor faults; kept generic on purpose,
    # because guessing a specific cause we cannot verify would mislead.
    "5:40": "Water supply problem — check the reservoir and connection.",
    "5:50": "Temperature sensor fault.",
    # module 7 - cycle/state faults
    "7:41": "Brew cycle could not start. Check that the pitcher is seated.",
    "7:50": "Brew was interrupted.",
    "7:60": "Cleaning or descale cycle required.",
}

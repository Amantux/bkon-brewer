#!/usr/bin/env python3
"""Brewer -> host event parsing.

    python3 tests/test_events.py

The failure mode this guards is a firmware message we do not recognise. It must
degrade to UNKNOWN-with-raw-text, never an exception -- an unhandled event is a
missing feature, a crash mid-brew is a ruined pot and a stuck integration.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer.protocol.events import (        # noqa: E402
    BrewerEvent, EventType, describe_error, parse_event)

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


print("connection state")
check("is_connected:1", parse_event("is_connected:1").type, EventType.CONNECTED)
check("is_connected:0", parse_event("is_connected:0").type, EventType.DISCONNECTED)

print("\nbrew progress")
check("stepCompleted", parse_event("stepCompleted").type, EventType.STEP_COMPLETED)
check("recipeCompleted", parse_event("recipeCompleted").type,
      EventType.RECIPE_COMPLETED)

print("\ndialog text is URL-decoded back to something readable")
e = parse_event("dialog:Add%20grounds%20and%20press%20start")
check("type", e.type, EventType.DIALOG)
check("decoded", e.text, "Add grounds and press start")
check("apostrophe round-trips",
      parse_event("dialog:Grandma%27s%20blend").text, "Grandma's blend")

print("\nnotify")
check("plain notify", parse_event("notify:Recipe Saved").type, EventType.NOTIFY)
check("carries its text", parse_event("notify:Recipe Saved").text, "Recipe Saved")

print("\nerrors keep their identifier even when we have no mapping")
e = parse_event("notify:(C:45 M:2) Descale Finished. Empty and clean pitcher.")
check("recognised as error", e.type, EventType.ERROR)
check("code extracted", e.code, "C:45 M:2")
check("mapped to a paraphrase",
      e.text.startswith("Descale finished"), True)

e = parse_event("(C:99 M:5) something new")
check("bare error line is still an error", e.type, EventType.ERROR)
check("unmapped code keeps the raw text", "something new" in e.text, True)
check("and still reports the identifier", e.code, "C:99 M:5")

print("\ndescribe_error")
check("known code", describe_error(2, 45).startswith("Descale finished"), True)
check("unknown code degrades legibly",
      describe_error(9, 9), "Brewer error C:9 M:9")

print("\nunknown input never raises")
for junk in ("", "garbage", "weird:payload:with:colons", "menu_list:[]"):
    e = parse_event(junk)
    check(f"{junk!r} -> event, not exception", isinstance(e, BrewerEvent), True)
check("empty is UNKNOWN", parse_event("").type, EventType.UNKNOWN)
check("unrecognised prefix is UNKNOWN, raw preserved",
      parse_event("menu_list:[]").raw, "menu_list:[]")

print("\ndevice discovery")
check("new_device", parse_event("new_device:AA:BB:CC").type, EventType.DEVICE_FOUND)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

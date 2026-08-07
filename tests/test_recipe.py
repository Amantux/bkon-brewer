#!/usr/bin/env python3
"""Recipe encoding tests.

    python3 tests/test_recipe.py

The anchor is the one complete command literal in the vendor app:

    <PG><PS>50</PS><TM>10</TM><DET>0</DET><CONTR>0</CONTR></PG>

If our encoder reproduces that byte for byte from the equivalent inputs, the
tag-casing and ordering rules are right. Everything else here guards a rule that
fails invisibly — a recipe that encodes almost correctly still brews, just not
the drink that was asked for, and the only symptom is disappointing coffee.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer.protocol import recipe as r      # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"  FAIL {name}:\n         got  {got!r}\n         want {want!r}")


print("the anchor: reproduce the vendor app's own purge literal")
step = r.Step(r.StepType.PURGE, {"ps": 50, "tm": 10, "det": 0, "contr": 0})
check("purge encodes to the documented literal",
      r.encode_command(step),
      "<PG><PS>50</PS><TM>10</TM><DET>0</DET><CONTR>0</CONTR></PG>")

print("\nzero-valued size keys are dropped, not sent as 0")
# Absent and zero mean different things to the firmware. This is the rule most
# likely to be "simplified away" by a reimplementation, and it is silent.
check("zero fill volume disappears",
      r.Step(r.StepType.FILL, {"fwv": 0, "rwv": 250}).normalised(),
      {"rwv": "250"})
check("zero pressure disappears",
      r.Step(r.StepType.PURGE, {"ps": 0, "tm": 10}).normalised(),
      {"tm": "10"})
check("but det=0 is kept - it is a flag, not a size",
      r.Step(r.StepType.PURGE, {"det": 0, "tm": 5}).normalised(),
      {"det": "0", "tm": "5"})
check("non-zero values survive",
      r.Step(r.StepType.FILL, {"fwv": 250, "rwv": 30, "dl": 5}).normalised(),
      {"fwv": "250", "rwv": "30", "dl": "5"})

print("\neverything is stringified")
vals = r.Step(r.StepType.START, {"tmp": 205}).normalised()
check("numbers become strings", vals, {"tmp": "205"})
check("and are genuinely str", all(isinstance(v, str) for v in vals.values()), True)

print("\nbrew-out is appended when missing, and never duplicated")
check("appended", [s["type"] for s in r.prepare([r.start(205)])],
      ["start", "bo"])
check("with the default brew time",
      r.prepare([r.start(205)])[-1]["values"], {"bt": "4"})
check("not duplicated when already present",
      [s["type"] for s in r.prepare([r.start(205), r.brew_out(6)])],
      ["start", "bo"])
check("and an explicit brew time is respected",
      r.prepare([r.start(205), r.brew_out(6)])[-1]["values"], {"bt": "6"})

print("\nmanual stop never reaches the device")
# The firmware has no manual-stop concept. The app fakes it with a dialog and
# drops the flag. A reimplementation that passes manstop through would produce
# a purge the brewer silently ignores the flag on -- looking like it worked.
out = r.prepare([r.purge(pressure=50, time_seconds=10, manual_stop=True)])
check("manstop is not on the wire", "manstop" in out[0]["values"], False)
check("it becomes a dialog instead",
      out[0]["values"].get("dialog"), r.MANUAL_STOP_DIALOG)
check("pressure and time are carried over",
      (out[0]["values"].get("ps"), out[0]["values"].get("tm")), ("50", "10"))
check("manstop=False also leaves nothing behind",
      "manstop" in r.prepare([r.purge(50, 10)])[0]["values"], False)

print("\ndialog text is URL-encoded, apostrophes included")
# quote() leaves apostrophes alone by default; the app escapes them separately
# because an unescaped one breaks its own single-quoted bridge call.
check("spaces encode",
      r.prepare([r.dialog("Add grounds")])[0]["values"]["text"],
      "Add%20grounds")
check("apostrophes encode to %27",
      r.prepare([r.dialog("Grandma's blend")])[0]["values"]["text"],
      "Grandma%27s%20blend")
check("and nothing is left raw",
      "'" in r.prepare([r.dialog("it's")])[0]["values"]["text"], False)

print("\nstart is rebuilt, keeping only a rounded temperature")
s = r.prepare([r.Step(r.StepType.START, {"tmp": 204.6, "ps": 99})])[0]
check("temperature is rounded", s["values"], {"tmp": "205"})
check("stray keys are discarded", "ps" in s["values"], False)

print("\nsize limit is a build-time error, not a brew-time surprise")
small = [r.start(205), r.fill(250), r.vacuum(50, 30)]
check("a normal recipe validates", isinstance(r.validate(small), str), True)
big = [r.dialog("x" * 40) for _ in range(20)]
try:
    r.validate(big)
    check("an oversized recipe raises", False, True)
except r.RecipeTooLarge as ex:
    check("an oversized recipe raises", True, True)
    check("and the message says what to do",
          "Consolidate" in str(ex), True)

print("\nwire form is XML step-tags, matching what the app converts JSON to")
# The app builds tags dynamically (type.toUpperCase()), so a whole recipe on the
# wire looks like the manual command literal, concatenated -- not JSON.
wire = r.encode_wire([r.start(205), r.fill(250, rinse_volume_ml=30),
                      r.purge(50, 10, detect=True)])
check("starts with the Start tag", wire.startswith("<START><TMP>205</TMP></START>"), True)
check("fill values are uppercased tags", "<FR><FWV>250</FWV><RWV>30</RWV></FR>" in wire, True)
check("purge matches the app's own tag form",
      "<PG><PS>50</PS><TM>10</TM><DET>1</DET></PG>" in wire, True)
check("brew-out is appended in tag form", wire.endswith("<BO><BT>4</BT></BO>"), True)
check("no JSON leaks into the wire form", "{" not in wire and "[" not in wire, True)
check("the JSON encode is still available for the size check",
      r.encode([r.start(205)]).startswith("["), True)

print("\nframing")
check("abort frame", r.ABORT, "{msg:1:<ABORT></ABORT>}")
check("cancel frame", r.CANCEL, "{msg:1:<CANCEL></CANCEL>}")
check("arbitrary payload", r.frame("<X></X>"), "{msg:1:<X></X>}")

print("\na realistic recipe round-trips to valid JSON")
full = [r.start(205), r.fill(250, rinse_volume_ml=30), r.vacuum(50, 30),
        r.purge(50, 10, detect=True), r.dialog("Add grounds")]
payload = r.validate(full)
parsed = json.loads(payload)
check("parses", isinstance(parsed, list), True)
check("brew-out was appended", parsed[-1]["type"], "bo")
check("step order preserved",
      [s["type"] for s in parsed],
      ["start", "fr", "vc", "pg", "dialog", "bo"])
check("comfortably inside the limit", len(payload.encode()) < r.MAX_RECIPE_BYTES, True)
check("every value is a string",
      all(isinstance(v, str) for s in parsed for v in s["values"].values()), True)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

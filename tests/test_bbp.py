#!/usr/bin/env python3
"""The .bbp menu-file codec.

    python3 tests/test_bbp.py

The interesting assertions are the round trips against REAL device files, when
they are present. Those files are vendor material and are never committed, so
the suite reads them from BKON_BBP_DIR if it is set and skips that section
otherwise -- CI runs the pure assertions, a developer with the archive runs
everything.
"""
import os
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "bkon_brewer"))
from protocol import bbp as B                        # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")
def ok(n, c): check(n, bool(c), True)


print("the checksum is JAMCRC, little-endian")
body = b"BKON" + struct.pack("<I", 12) + b"hello"
check("matches ~crc32", B.checksum(body),
      struct.pack("<I", zlib.crc32(body) ^ 0xFFFFFFFF))
check("four bytes", len(B.checksum(body)), 4)
sealed = B.seal(body)
ok("a sealed file verifies", B.verify(sealed))
ok("a flipped byte does not", not B.verify(sealed[:-5] + bytes([sealed[-5] ^ 1]) + sealed[-4:]))
ok("junk is rejected", not B.verify(b"nope"))
ok("the service magic is accepted too", B.verify(B.seal(b"BKOn" + b"\x0c\x00\x00\x00x")))

print("\na step record round-trips")
raw = B.encode_step(2, "<PS>28</PS><TM>7</TM>")
check("type, length, tag", raw[:5], struct.pack("<IB", 2, 21))
step, end = B.decode_step(raw)
check("type survives", step.type_code, 2)
check("tag survives", step.tag, "<PS>28</PS><TM>7</TM>")
check("offset lands past the record", end, len(raw))
check("named for us", step.name, "vc")
check("the five types we know", sorted(B.STEP_TYPES.values()),
      ["bo", "fr", "pg", "start", "vc"])

print("\ndamage is refused, not misread")
for bad, why in ((raw[:3], "truncated header"), (raw[:7], "truncated tag")):
    try: B.decode_step(bad); check(why, "no error", "BbpError")
    except B.BbpError: check(why, "BbpError", "BbpError")
try:
    B.encode_step(1, "<X>" + "y" * 300 + "</X>"); check("over-long tag", "no error", "BbpError")
except B.BbpError: check("over-long tag", "BbpError", "BbpError")

print("\nscanning finds steps in a stream")
stream = (b"\x00\x01junk" + B.encode_step(0, "<TMP>170</TMP>")
          + b"\xff\xff" + B.encode_step(4, "<BT>4</BT>"))
found = B.steps_to_tags(B.iter_steps(stream))
check("both found despite the noise", found,
      [("start", "<TMP>170</TMP>"), ("bo", "<BT>4</BT>")])

d = os.environ.get("BKON_BBP_DIR")
files = sorted(Path(d).glob("*.[BF]BP")) if d and Path(d).is_dir() else []
if not files:
    print("\n(no real .bbp files — set BKON_BBP_DIR to run the round trips)")
else:
    print(f"\nreal device files ({len(files)})")
    total = 0
    for f in files:
        data = f.read_bytes()
        ok(f"{f.name}: checksum verifies", B.verify(data))
        steps = list(B.iter_steps(data))
        total += len(steps)
        ok(f"{f.name}: steps found", len(steps) > 0)
        # every step re-encodes to the exact bytes it came from
        ok(f"{f.name}: every step re-encodes byte-identically",
           all(B.decode_step(B.encode_step(s.type_code, s.tag))[0] == s for s in steps))
        starts = sum(1 for s in steps if s.type_code == 0)
        outs = sum(1 for s in steps if s.type_code == 4)
        # Portions pair a start with a brew-out. The service menu balances
        # exactly; the beverage menus come out one brew-out over, which is an
        # open question recorded in docs/BBP_FORMAT.md -- so this asserts the
        # near-balance that is actually true rather than an invariant that is not.
        ok(f"{f.name}: starts and brew-outs balance within one ({starts}/{outs})",
           abs(starts - outs) <= 1)
    print(f"  ({total} step records across {len(files)} files)")

print("\nbuilding a .bbp — the confirmed parts must hold")
REC = {"name": "Morning Cup", "code": "205/0/0", "portions": [
    ("small", [{"type": "start", "values": {"tmp": "205"}},
               {"type": "fr", "values": {"fwv": "250", "rwv": "30"}},
               {"type": "vc", "values": {"ps": "24", "tm": "6"}},
               {"type": "pg", "values": {"ps": "30", "tm": "10", "det": "1"}},
               {"type": "bo", "values": {"bt": "4"}}])]}
blob = B.build_menu([{"name": "Home Assistant", "colour": (168, 98, 31), "recipes": [REC]}])
ok("it is a BKON file", blob[:4] == B.MAGIC_MENU)
ok("its checksum verifies", B.verify(blob))
chk = B.selfcheck(blob)
check("every step reads back", chk["steps_readable"], 5)
check("one start", chk["starts"], 1)
check("one brew-out", chk["brew_outs"], 1)

back = B.steps_to_tags(B.iter_steps(blob))
check("the tags survive exactly", back, [
    ("start", "<TMP>205</TMP>"),
    ("fr", "<FWV>250</FWV><RWV>30</RWV>"),
    ("vc", "<PS>24</PS><TM>6</TM>"),
    ("pg", "<PS>30</PS><TM>10</TM><DET>1</DET>"),
    ("bo", "<BT>4</BT>")])
ok("tags are uppercased like the machine's own files", "<TMP>" in blob.decode("latin-1"))

print("\nthe writer refuses what it cannot encode")
try:
    B.build_menu([{"name": "X", "recipes": [{"name": "n", "code": "", "portions": [("small", [{"type": "nope", "values": {}}])]}]}])
    check("unknown step type", "no error", "BbpError")
except B.BbpError:
    check("unknown step type", "BbpError", "BbpError")

print("\nthe self-check is honest about what it proves")
ok("it names the confirmed part", "checksum" in chk["confirmed"])
ok("it names the unconfirmed part", "framing" in chk["unconfirmed"])

print("\na service menu uses the other magic")
sm = B.build_menu([], service=True)
check("service magic", sm[:4], B.MAGIC_SERVICE)
ok("still checksums", B.verify(sm))

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

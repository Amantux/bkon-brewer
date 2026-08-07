#!/usr/bin/env python3
"""Recipe export/import — the git round-trip.

    python3 tests/test_recipe_files.py

One file per recipe, deterministic bytes so an unchanged library re-exports to a
clean git status, a true mirror (stale files pruned), and a tolerant import that
skips a bad file rather than refusing the whole set. Uses a temp directory; no
Home Assistant, no yaml.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import recipe_files as F  # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


RECORDS = [
    {"name": "Morning Cup", "steps": [{"type": "start", "values": {"tmp": 200}}]},
    {"name": "Espresso Style", "steps": [{"type": "vc", "values": {"ps": 30, "tm": 6}}]},
]


print("export writes one file per recipe, cleanly named")
with tempfile.TemporaryDirectory() as d:
    r = F.write_recipes(d, RECORDS)
    check("both written", r["total"], 2)
    check("slug filenames", set(p.name for p in Path(d).glob("*.json")),
          {"morning_cup.json", "espresso_style.json"})

    print("\nre-export of an unchanged library touches nothing (clean git status)")
    r2 = F.write_recipes(d, RECORDS)
    check("nothing rewritten", r2["written"], [])

    print("\nediting one recipe is a one-file change")
    changed = [dict(RECORDS[0], steps=[{"type": "start", "values": {"tmp": 205}}]),
               RECORDS[1]]
    r3 = F.write_recipes(d, changed)
    check("only the edited file rewritten", r3["written"], ["morning_cup.json"])

    print("\nprune makes it a true mirror")
    r4 = F.write_recipes(d, [RECORDS[1]])          # dropped Morning Cup
    check("stale file removed", r4["removed"], ["morning_cup.json"])
    check("only one file left", len(list(Path(d).glob("*.json"))), 1)

print("\nround-trip: export then import returns the same recipes")
with tempfile.TemporaryDirectory() as d:
    F.write_recipes(d, RECORDS)
    back, errors = F.read_recipes(d)
    check("no errors", errors, [])
    check("both recipes read", sorted(r["name"] for r in back),
          ["Espresso Style", "Morning Cup"])
    check("steps preserved",
          next(r for r in back if r["name"] == "Morning Cup")["steps"],
          RECORDS[0]["steps"])

print("\nimport tolerates a bad file, skips it, names it")
with tempfile.TemporaryDirectory() as d:
    F.write_recipes(d, RECORDS)
    (Path(d) / "broken.json").write_text("{ not valid json", encoding="utf-8")
    (Path(d) / "notarecipe.json").write_text('{"foo": 1}', encoding="utf-8")
    back, errors = F.read_recipes(d)
    check("good recipes still imported", len(back), 2)
    check("bad files reported", len(errors), 2)
    check("error names the file", any("broken.json" in e for e in errors), True)

print("\nto_text renders a readable document with units")
txt = F.to_text(RECORDS)
check("has a header", "BKON Brewer" in txt, True)
check("names each recipe", "Morning Cup" in txt and "Espresso Style" in txt, True)
check("spells out step names", "Start" in txt and "Vacuum" in txt, True)
check("shows units", "°F" in txt, True)
check("shows a byte size", "bytes" in txt, True)
check("empty library is handled", "no recipes" in F.to_text([]), True)

print("\nreading a missing directory is an error, not a crash")
recs, errs = F.read_recipes("/nonexistent/place")
check("empty records", recs, [])
check("error explains", "does not exist" in errs[0], True)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

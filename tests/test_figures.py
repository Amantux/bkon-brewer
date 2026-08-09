#!/usr/bin/env python3
"""Deciding which pages are pictures, and how a described one is indexed.

    python3 tests/test_figures.py

The premise, measured over the 49 stored PDFs: 717 pages, and 620 of them carry
a diagram, a screenshot or a photograph. One page of the air/water flow deck has
226 characters of text and a full hydraulic schematic with a dozen labelled
valves on it. A text index of this corpus indexes the captions of a picture
book, which is why 16 documents had two passages or fewer.

So `visual` is the load-bearing judgement in the whole feature: too eager and
600 title slides get sent to a vision model at a call each; too shy and the
schematics stay invisible. PyMuPDF is not installed in CI, so the parts that
need a real PDF are skipped there and the pure decisions are tested here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "lightrag_service"))

import figures as F                                   # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


def ok(name, cond):
    check(name, bool(cond), True)


print("a model that says there is nothing here is believed")
# Cheap to get wrong in both directions, so it is read loosely: a page wrongly
# kept is clutter, a page wrongly dropped is invisible.
for said in ("SKIP", "skip", " SKIP ", "SKIP.", '"SKIP"', "SKIP - title slide"):
    ok(f"{said!r} is a skip", F.is_skip(said))
for said in ("A wiring diagram of the tower.", "", "This page skips the purge step.",
             "Skipping is covered on page 4."):
    ok(f"{said[:34]!r} is not a skip", not F.is_skip(said))

print("\na described picture is a passage like any other")
# Figures are indexed beside the prose on purpose: a question about a drain
# line should be able to match a schematic, and it only can if the schematic's
# description is ranked against the text rather than kept in its own world.
p = F.as_passage("Service Manual", 12, "A flow schematic showing V5.", "service-manual-p12")
check("it names its document", p["doc"], "Service Manual")
check("and its page, so a citation lands there", p["page"], 12)
check("the description is the searchable text", p["text"], "A flow schematic showing V5.")
check("it is marked as a picture", p["kind"], "figure")
check("and carries the id to fetch it by", p["figure"], "service-manual-p12")

print("\nthe thresholds are stated, not scattered")
ok("a minimum image size", F._MIN_IMAGE_PX >= 100)
ok("a minimum drawing count for vector diagrams", F._MIN_DRAWINGS > 0)
ok("a render resolution that can show UI text", F.RENDER_DPI >= 100)
# Big enough to read a screenshot, small enough not to store megabytes a page.
ok("but not a wasteful one", F.RENDER_DPI <= 200)

print("\nthe caption prompt asks for something searchable")
# "Describe this image" returns prose about layout. What is wanted is the words
# a technician would type when they have the problem the page solves.
for want in ("error codes", "wiring diagram", "screenshot", "SKIP"):
    ok(f"it mentions {want}", want.lower() in F.CAPTION_PROMPT.lower())
ok("it asks for plain prose, since the text is indexed",
   "no markdown" in F.CAPTION_PROMPT.lower())
ok("there is a short label prompt too", len(F.LABEL_PROMPT) > 40)

print("\nreading a real PDF")
try:
    import pymupdf                                    # noqa: F401
except ImportError:
    print("  -- PyMuPDF not installed here; extraction not exercised")
else:
    import zlib
    # A one-page PDF with a line of text and no picture, built by hand so the
    # test needs no fixture file.
    body = b"BT /F1 12 Tf 72 720 Td (Hello brewer) Tj ET"
    pdf = (b"%PDF-1.4\n"
           b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
           b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
           b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
           b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
           b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
           b"5 0 obj<</Length " + str(len(body)).encode() + b">>stream\n"
           + body + b"\nendstream endobj\ntrailer<</Root 1 0 R>>")
    ex = F.extract("Sample", pdf, render=False)
    check("one page", len(ex.pages), 1)
    check("numbered from one, as a citation says it", ex.pages[0].number, 1)
    ok("its text comes out", "Hello brewer" in ex.pages[0].text)
    check("a page of plain text is not a picture", ex.pages[0].visual, False)
    check("so there is nothing to describe", len(ex.visual_pages), 0)

print("\nreading the data back out of a picture")
# A description is prose, and prose loses what is most useful on these pages:
# the wording the machine puts on its own screen, part numbers, valve labels.
# The error-code pages are the case in point -- their left half is real PDF
# text, but the photograph of the display carries the remedy and the service
# number, and that text is nowhere else.
good = """```json
{"visible_text": "Chamber Not Sealed (C:3 M:5). Brew chamber not closed. Call 1-855-353-7378.",
 "codes": [{"code": "C:3 M:5", "title": "Chamber Not Sealed",
            "cause": "A vacuum cannot be created", "remedy": "Inspect the purge valve",
            "message": "Brew chamber not closed."}],
 "parts": [{"number": "19006211", "name": "Pump, Vacuum 24VDC"}],
 "labels": [{"label": "V5", "name": "Proportional Valve"}]}
```"""
f = F.parse_facts(good)
check("the transcription survives fencing",
      f["visible_text"].startswith("Chamber Not Sealed"), True)
check("one code", len(f["codes"]), 1)
check("with its remedy", f["codes"][0]["remedy"], "Inspect the purge valve")
check("and the machine's own words", f["codes"][0]["message"], "Brew chamber not closed.")
check("one part", f["parts"][0]["number"], "19006211")
check("one label", f["labels"][0]["label"], "V5")

print("\nbad output costs one page, not the run")
for bad in ("I could not read this page", "", "null", "[]", "{oops",
            '{"codes": "not a list"}'):
    got = F.parse_facts(bad)
    check(f"{bad[:24]!r} yields nothing", (got["codes"], got["parts"], got["labels"]),
          ([], [], []))

print("\na row with no identity is dropped, not kept blank")
# A part with no number, a code with no code: they cannot be looked up and
# would only pollute the table.
f = F.parse_facts('{"parts": [{"number": "", "name": "mystery"},'
                  ' {"number": "19006169", "name": "Elbow"}],'
                  ' "codes": [{"code": "", "title": "nameless"}],'
                  ' "labels": [{"label": "", "name": "unknown"}]}')
check("the nameless part is gone", [p["number"] for p in f["parts"]], ["19006169"])
check("the codeless code is gone", f["codes"], [])
check("the unlabelled label is gone", f["labels"], [])

print("\nthe prompt forbids inventing an identifier")
low = F.EXTRACT_PROMPT.lower()
ok("it says never invent", "never invent" in low)
ok("it asks for verbatim transcription", "verbatim" in low)
ok("it says not to guess a label's meaning", "do not guess" in low)
ok("it names the keys it wants", all(k in F.EXTRACT_PROMPT
   for k in ("visible_text", "codes", "parts", "labels")))

print("\nfinding the pages that read together")
# An unillustrated page breaks a run. That sounds crude and is the whole trick:
# in the error-code deck each fault gets a symptom page and a remedy page, with
# an unillustrated page between faults -- so adjacency separates the faults
# exactly where a human would.
check("consecutive pages group",  F.runs_of([1, 2, 3]), [[1, 2, 3]])
check("a gap starts a new run",   F.runs_of([2, 4, 5, 7, 8, 10, 11, 13]),
      [[2], [4, 5], [7, 8], [10, 11], [13]])
check("order does not matter",    F.runs_of([5, 4, 2]), [[2], [4, 5]])
check("duplicates collapse",      F.runs_of([3, 3, 4]), [[3, 4]])
check("nothing in, nothing out",  F.runs_of([]), [])

print("\na run is named by what its pages have in common")
check("a fault and its remedy",
      F.name_run(["Purge valve and C:3 M:5 error",
                  "Purge valve cleaning and interface guide"]),
      "purge valve")
check("a phase-by-phase walkthrough",
      F.name_run(["BKON Craft Brewer Brew Cycle-Start schematic",
                  "BKON Craft Brewer Brew Cycle schematic",
                  "Brew Cycle-Vacuum flow schematic",
                  "BKON Craft Brewer Brew Cycle-Purge schematic"]),
      "brew cycle schematic")
# The brand name is on almost every label, so it says nothing about which run
# a page belongs to and must not become the name of every sequence.
ok("the brand name is never the name",
   "bkon" not in F.name_run(["BKON Craft Brewer schematic",
                             "BKON Craft Brewer photo"]))
# Pages that merely sit next to each other are a stretch of a document, not a
# subject. Better to say "pages 12-18" than to invent a title for them.
check("unrelated pages get no name",
      F.name_run(["Spare parts list", "A wiring harness", "Descaling menu"]), "")
check("and nothing at all is not a name", F.name_run([]), "")
# A word on one page of ten is not what the run is about, however distinctive.
one_of_ten = F.name_run(["purge valve"] + ["heater element %d" % i for i in range(9)])
ok("a word on one page does not name the run", "purge" not in one_of_ten)
ok("but the words on nine of ten do", "heater" in one_of_ten)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

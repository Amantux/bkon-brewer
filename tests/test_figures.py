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

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

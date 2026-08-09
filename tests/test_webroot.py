#!/usr/bin/env python3
"""The served page's structure and CSS scoping.

    python3 tests/test_webroot.py

Two real outages came from this file and neither was a logic bug:

  * handlers for removed markup called addEventListener on null, which threw and
    killed the rest of the script -- so the builder rendered nothing;
  * the page-switching rule was a bare `section{display:none}`, which hid every
    NESTED section too, so the recipe builder and store disappeared the moment
    they became <section class="zone">.

Both are invisible to a logic test and obvious to a structural one.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "addon" / "webroot" / "index.html"

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")
def ok(n, c): check(n, bool(c), True)

s = HTML.read_text()
css = re.search(r"<style>(.*?)</style>", s, re.S).group(1)
scripts = re.findall(r"<script>(.*?)</script>", s, re.S)

print("every element the scripts reach for actually exists")
ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', s))
asked = set()
for x in scripts:
    asked |= set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', x))
    asked |= set(re.findall(r'getElementById\("([A-Za-z0-9_-]+)"\)', x))
check("no reference to a removed element", sorted(asked - ids), [])

print("\npage switching cannot hide nested content")
bare = [l.strip() for l in css.split("\n")
        if re.search(r"(^|[,{}\s])section\s*\{", l)
        and "main >" not in l and "main>" not in l]
check("the page rule is scoped to main's children", bare, [])
ok("the scoped rule is present", "main > section{" in css and "display:none" in css)

print("\nthe builder and the recipe store are inside the studio page")
studio = s[s.index('<section id="studio"'):]
studio = studio[:studio.index("<!-- RECIPES -->")] if "<!-- RECIPES -->" in studio else studio
for part in ("stuPalette", "stuSteps", "stuStarts", "stuBlank", "stuLibList", "stuName"):
    ok(f"{part} present", part in studio)

print("\nevery nav target resolves to a page, and every page is reachable")
navs = set(re.findall(r'data-nav="([a-z]+)"', s))
pages = set(re.findall(r'<section id="([a-z]+)"', s))
check("no nav points at a missing page", sorted(navs - pages), [])
check("no page is unreachable", sorted(pages - navs), [])

print("\nmarkup is balanced")
# Count tags in the markup only. The stylesheet and its comments mention things
# like `<main>` and `section`, which would otherwise be counted as elements.
body = re.sub(r"<style>.*?</style>", "", s, flags=re.S)
body = re.sub(r"<script>.*?</script>", "", body, flags=re.S)
for tag in ("section", "div", "form", "details", "aside", "main", "nav", "select"):
    o = len(re.findall(rf"<{tag}[ >]", body)); c = body.count(f"</{tag}>")
    check(f"<{tag}> balanced", o, c)
check("script tags balanced", s.count("<script>"), s.count("</script>"))

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

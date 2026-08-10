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

print("\nno interactive element is left without a handler")
# The mirror of the check above, and the one that was missing: a <form> or a
# button with an id that no script ever touches is dead. A form is the worse
# case -- submitting it navigates, which inside the ingress iframe reloads the
# page and discards whatever the user was building. That is exactly how the
# studio's "describe it in words" form sat broken.
scripts = "\n".join(scripts)
orphans = []
for m in re.finditer(r'<(form|button|select)\b[^>]*\bid="([A-Za-z0-9_-]+)"', s):
    tag, eid = m.group(1), m.group(2)
    if eid not in scripts:
        orphans.append(f"<{tag} id={eid}>")
check("every form/button/select with an id is wired up", orphans, [])
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

print("\nthe turn shows its working, then folds it away")
# The point of the trace is that it accumulates. A renderer that overwrites one
# line looks identical in a screenshot and is useless in practice, so these
# assert the shape that makes it a list.
ok("there is a live trace renderer", "function renderTrace(" in s)
ok("it renders one element per step", "steps.map(" in s)
ok("a finished step is marked done", 'st.done?" done"' in s)
ok("the running step is announced to screen readers", 'aria-live","polite"' in s)

ok("there is a collapsed summary", "function workSummary(" in s)
ok("it uses a native disclosure, so it is keyboard-operable",
   "<details" in s and "<summary>" in s)
ok("the answer replaces the trace rather than sitting under it",
   s.index("function workSummary(") > 0 and "stopPoll();" in s)
ok("polling stops before the answer is rendered",
   s.index("stopPoll();\n      if(typeof window.bkonMd") > 0)

# Both sides name a tool the same way, or the same step reads differently
# depending on whether you caught it live or expanded it later.
ok("the browser has its own wording map", "const TOOL_SAYS" in s)
for tool in ("answer_docs", "adjust_recipe", "list_recipes", "brew_recipe"):
    ok(f"{tool} has plain-language wording", f"{tool}:" in s)

# A failed turn keeps the trace: "it died reading the manuals" beats a bare
# error message with no indication of how far it got.
ok("a failed turn keeps its trace", 'classList.add("failed")' in s)
ok("and shows the error beneath it", "cmp-err" in s)

print("\nevery class the trace uses is actually styled")
for cls in ("cmp-trace", "cmp-step", "cmp-tick", "cmp-work", "cmp-worklist", "cmp-err"):
    ok(f".{cls} has a rule", f".{cls}{{" in s or f".{cls} " in s)
ok("the pulse respects reduced motion",
   "prefers-reduced-motion" in s and "cmp-pulse" in s)

print("\nsources are folded away, and unchanged when opened")
# An answer citing four pages, each carrying its own figure, was taller than
# the answer itself. Sources are for checking a claim -- something you do
# sometimes, not every time -- so they start closed.
ok("sources are a disclosure", "<details class=\"dg-cites\">" in s)
ok("the summary counts them", "Sources \u00b7 ${(d.sources||[]).length}" in s)
ok("it does not start open", 'class="dg-cites" open' not in s)
# Opening must show exactly what it always showed: the same citation markup,
# same excerpts, same figures.
ok("the citations themselves are untouched", "${cites}" in s)
ok("and keep their own list styling", ".dg-citelist{" in s)

# The buttons inside a closed <details> are still in the DOM, so they are still
# bound; a citation that only worked once opened would be a trap.
ok("citation buttons are bound regardless", 'querySelectorAll("button[data-doc]")' in s)

print("\nthe disclosure is operable without a mouse")
ok("the marker is replaced, not left doubled", "::-webkit-details-marker{display:none}" in s)
ok("keyboard focus is visible", ".dg-citehead:focus-visible{" in s)
ok("and the rotation respects reduced motion",
   "prefers-reduced-motion" in s and ".dg-citehead::before{transition:none}" in s)
# Images inside a closed disclosure must not be fetched until it opens.
ok("figures load lazily", 'loading="lazy"' in s)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

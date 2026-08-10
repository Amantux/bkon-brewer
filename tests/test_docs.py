#!/usr/bin/env python3
"""The wiki describes what is actually here.

    python3 tests/test_docs.py

Documentation rots more quietly than code: nothing fails when a doc starts
describing a version that no longer exists, and the person it misleads is
usually someone returning to the project cold — which is exactly who it was
written for.

This checks the claims that are checkable. Not prose or judgement: file paths,
counts, and whether the things a doc says exist actually do.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

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


print("every document a reader is pointed at exists")
missing = []
for f in list(DOCS.glob("*.md")) + [ROOT / "README.md"]:
    for m in re.finditer(r"\[[^\]]+\]\((?!https?:|#)([^)#]+)", f.read_text()):
        if not (f.parent / m.group(1)).resolve().exists():
            missing.append(f"{f.name} -> {m.group(1)}")
check("no broken links", missing, [])

print("\nthe index points at every document, and only real ones")
index = (DOCS / "README.md").read_text()
for name in sorted(p.name for p in DOCS.glob("*.md")):
    if name in ("README.md", "WIKI_PLAN.md", "MOBILE_AUDIT.md"):
        continue                       # the index, and two marked proposals
    ok(f"{name} is linked from the index", name in index)

print("\nproposals are labelled as proposals")
# 116 KB of unapplied plans read as specifications to someone returning cold.
for name in ("WIKI_PLAN.md", "MOBILE_AUDIT.md"):
    head = (DOCS / name).read_text()[:600]
    ok(f"{name} says what it is", "Status:" in head)

print("\nthe paths the architecture doc names are the paths the code uses")
arch = (DOCS / "ARCHITECTURE.md").read_text()
server = (ROOT / "addon" / "lightrag_service" / "server.py").read_text()
run_sh = (ROOT / "addon" / "run.sh").read_text()
for path, where in (("/data/kb.json", server),
                    ("/share/bkon_lightrag/originals", server),
                    ("/share/bkon_lightrag/figures", server),
                    ("/share/bkon_lightrag/rag_storage", run_sh)):
    ok(f"{path} is real", path in where)
    # The doc draws these as a tree, so the full string is split across lines.
    # Checked the way a reader reads it: the root, and the leaf under it.
    root, _, leaf = path.rpartition("/")
    ok(f"{path} is documented", root in arch and leaf in arch)

print("\ncounts the docs quote are the counts the project has")
# A stale number is worse than none: it is quoted with confidence.
suite = subprocess.run([sys.executable, str(ROOT / "tests" / "run_all.sh")],
                       capture_output=True, text=True)
listed = len(list((ROOT / "tests").glob("test_*.py")))
ok("there are tests to count", listed > 20)
quoted = re.search(r"(\d+) assertions", (DOCS / "README.md").read_text())
ok("the README quotes an assertion count", quoted is not None)
ok("and the architecture doc quotes the same one",
   quoted and quoted.group(1) in arch)

print("\nthe tools the architecture doc lists are the tools that exist")
chat = (ROOT / "addon" / "lightrag_service" / "chat.py").read_text()
tools = set(re.findall(r'^\s*"([a-z_]+)": .args \{', chat, re.M))
ok("there are tools to list", len(tools) >= 10)
undocumented = sorted(t for t in tools if t not in arch)
check("every tool is documented", undocumented, [])

print("\nand the invariants it warns about are still true")
recipe = (ROOT / "custom_components" / "bkon_brewer" / "protocol" / "recipe.py").read_text()
ok("zero-valued size keys are still dropped", "_DROP_IF_ZERO" in recipe)
ok("sizes are still derived through a notional medium", "sizes_from" in recipe)
ok("apparmor is still a boolean",
   re.search(r"^apparmor:\s*(true|false)\s*$",
             (ROOT / "addon" / "config.yaml").read_text(), re.M) is not None)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

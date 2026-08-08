#!/usr/bin/env python3
"""Verify the add-on's vendored core matches the integration's source.

    python3 scripts/check_core_sync.py

The add-on must be buildable standalone (the Supervisor may build it locally),
so the pure logic it needs -- recipe encoding, the advisor, diagnostics,
templates -- is vendored into addon/lightrag_service/bkon_core/. That copy must
not drift from custom_components/bkon_brewer/. This fails CI if it has.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "custom_components" / "bkon_brewer"
CORE = ROOT / "addon" / "lightrag_service" / "bkon_core"

PAIRS = [
    (SRC / "advisor.py", CORE / "advisor.py"),
    (SRC / "diagnostics.py", CORE / "diagnostics.py"),
    (SRC / "templates.py", CORE / "templates.py"),
    (SRC / "nl_recipe.py", CORE / "nl_recipe.py"),
    (SRC / "app_recipe.py", CORE / "app_recipe.py"),
    (SRC / "protocol" / "recipe.py", CORE / "protocol" / "recipe.py"),
    (SRC / "protocol" / "events.py", CORE / "protocol" / "events.py"),
    (SRC / "protocol" / "bbp.py", CORE / "protocol" / "bbp.py"),
]

drift = 0
for src, core in PAIRS:
    if not core.exists():
        print(f"  MISSING {core.relative_to(ROOT)}"); drift += 1; continue
    if src.read_text() != core.read_text():
        print(f"  DRIFT   {core.relative_to(ROOT)} != {src.relative_to(ROOT)}"); drift += 1
    else:
        print(f"  ok      {core.relative_to(ROOT).name}")

if drift:
    print(f"\n{drift} file(s) out of sync. Run: cp the sources into bkon_core/.")
    sys.exit(1)
print("\nadd-on core is in sync with the integration.")

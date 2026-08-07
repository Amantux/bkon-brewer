"""Import the pure protocol modules without running the package __init__.

custom_components/bkon_brewer/__init__.py is the Home Assistant setup entry
point and legitimately imports HA and voluptuous. But the modules worth testing
-- the recipe encoder, the event parser, the framing splitter -- are pure, and
requiring a full Home Assistant install to run them would mean they stopped
being run, which is how a wire-format encoder rots silently.

So register a stand-in package whose __path__ points at the real directory.
Submodule imports resolve normally against the real files; the real __init__.py
is never executed. Nothing is mocked -- the code under test is the code that
ships.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "bkon_brewer"


def install() -> None:
    if "bkon_brewer" in sys.modules:
        return
    sys.path.insert(0, str(ROOT / "custom_components"))
    pkg = types.ModuleType("bkon_brewer")
    pkg.__path__ = [str(PKG)]
    sys.modules["bkon_brewer"] = pkg
    proto = types.ModuleType("bkon_brewer.protocol")
    proto.__path__ = [str(PKG / "protocol")]
    sys.modules["bkon_brewer.protocol"] = proto

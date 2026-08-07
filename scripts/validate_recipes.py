#!/usr/bin/env python3
"""Validate every recipe JSON file — for CI and for a pre-commit check.

    python3 scripts/validate_recipes.py recipes defaults custom_components/bkon_brewer/defaults

Each file must parse, name a recipe, and encode to a transmittable recipe within
the Bluetooth size limit. A recipe that cannot brew has no business being
committed as a default, and this is where that is caught — in review, not on the
machine. Exits non-zero if any file fails, naming each.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Register a stand-in package so the pure protocol module imports without the
# integration's Home Assistant dependencies (same shape as tests/_bootstrap.py).
import types
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "custom_components"))
if "bkon_brewer" not in sys.modules:
    _pkg = types.ModuleType("bkon_brewer")
    _pkg.__path__ = [str(_ROOT / "custom_components" / "bkon_brewer")]
    sys.modules["bkon_brewer"] = _pkg
    _proto = types.ModuleType("bkon_brewer.protocol")
    _proto.__path__ = [str(_ROOT / "custom_components" / "bkon_brewer" / "protocol")]
    sys.modules["bkon_brewer.protocol"] = _proto

from bkon_brewer.protocol import recipe as R      # noqa: E402


def check_file(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as ex:
        return f"not valid JSON: {ex}"
    if not isinstance(data, dict) or not data.get("name"):
        return "missing a name"
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return "missing steps"
    try:
        typed = [R.Step(R.StepType(s["type"]), dict(s.get("values", {})))
                 for s in steps]
    except (KeyError, ValueError) as ex:
        return f"bad step: {ex}"
    try:
        payload = R.validate(typed)
    except R.RecipeTooLarge as ex:
        return str(ex)
    except Exception as ex:                          # noqa: BLE001
        return f"will not encode: {ex}"
    size = len(payload.encode("utf-8"))
    return None if size <= R.MAX_RECIPE_BYTES else f"{size} bytes, over limit"


def main(dirs: list[str]) -> int:
    files: list[Path] = []
    for d in dirs:
        p = Path(d)
        if p.exists():
            files.extend(sorted(p.glob("*.json")))
    if not files:
        print("No recipe files found.")
        return 0
    failed = 0
    for f in files:
        err = check_file(f)
        if err:
            failed += 1
            print(f"  FAIL {f}: {err}")
        else:
            print(f"  ok   {f}")
    print(f"\n{len(files) - failed}/{len(files)} recipe files valid.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["recipes"]))

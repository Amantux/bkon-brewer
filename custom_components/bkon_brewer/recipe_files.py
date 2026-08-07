"""Recipes on disk: one JSON file per recipe, for checking into git.

Home Assistant stores recipes in a single opaque `.storage` blob -- fine at
runtime, useless in a pull request. This mirrors the library to a directory of
`<slug>.json` files, pretty-printed and key-sorted, so a change to one recipe is
a one-file diff a human (or a reviewer) can read, and the whole set can be
committed.

Pure over the filesystem -- stdlib json only, no Home Assistant, no yaml -- so
the round-trip is testable with a temp directory. Callers run it off the event
loop via an executor.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_SAFE = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    return _SAFE.sub("_", (name or "").lower()).strip("_") or "recipe"


def write_recipes(directory: str, records: list[dict], *,
                  prune: bool = True) -> dict:
    """Write one file per recipe. Returns a report of what changed on disk.

    Deterministic output -- sorted keys, trailing newline -- so re-exporting an
    unchanged library produces byte-identical files and git shows nothing. With
    `prune`, files for recipes no longer in the library are removed, so the
    directory is a true mirror rather than an ever-growing pile.
    """
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    keep: set[str] = set()
    from . import app_recipe
    for rec in records:
        name = (rec.get("name") or "").strip()
        if not name:
            continue
        fname = f"{_slug(name)}.json"
        keep.add(fname)
        # Write the app's recipe-object shape so a file matches what the app
        # itself produces -- a single "standard" portion from our flat steps,
        # with the metadata fields the app carries.
        obj = app_recipe.to_app_recipe(
            name, [(app_recipe.DEFAULT_PORTION, rec.get("steps", []))],
            description=rec.get("description", ""))
        payload = json.dumps(obj, indent=2, sort_keys=True,
                             ensure_ascii=False) + "\n"
        path = d / fname
        # Only touch the file if the content actually changed, so mtimes and
        # git status stay quiet on a no-op export.
        if not path.exists() or path.read_text(encoding="utf-8") != payload:
            path.write_text(payload, encoding="utf-8")
            written.append(fname)

    removed: list[str] = []
    if prune:
        for existing in d.glob("*.json"):
            if existing.name not in keep:
                existing.unlink()
                removed.append(existing.name)

    return {"written": sorted(written), "removed": sorted(removed),
            "total": len(keep), "directory": str(d)}


# Unit labels for the text form, from docs/INTEL.md. A plain reader should see
# "205 °F" and "250 ml", not "tmp: 205" and "fwv: 250".
_UNITS = {"tmp": "°F", "fwv": "ml", "rwv": "ml", "dl": "s", "tm": "s",
          "ps": "", "bt": "s"}
_KEY_NAMES = {"tmp": "temperature", "fwv": "fill", "rwv": "rinse",
              "dl": "pause", "tm": "time", "ps": "pressure", "det": "detect",
              "manstop": "manual-stop", "bt": "brew", "text": "prompt"}
_STEP_NAMES = {"start": "Start", "fr": "Fill", "vc": "Vacuum", "pg": "Purge",
               "dialog": "Dialog", "bo": "Brew out"}


def to_text(records: list[dict]) -> str:
    """Render the whole library as one readable text document, for download.

    A plain .txt anyone can open, print, or paste -- names, steps spelled out
    with their units, and each recipe's Bluetooth byte size. Deliberately not
    JSON: this is the human copy, the files are the machine copy.
    """
    from .protocol import recipe as R           # local: keep the module import-light
    lines = ["BKON Brewer — Recipes", "=" * 40, ""]
    if not records:
        lines.append("(no recipes)")
        return "\n".join(lines) + "\n"
    for rec in records:
        name = rec.get("name", "(unnamed)")
        steps_raw = rec.get("steps", [])
        lines.append(name)
        lines.append("-" * len(name))
        for i, st in enumerate(steps_raw, 1):
            typ = st.get("type", "?")
            label = _STEP_NAMES.get(typ, typ)
            parts = []
            for k, v in st.get("values", {}).items():
                if k == "text":
                    parts.append(f'"{v}"')
                elif k in ("det", "manstop"):
                    if str(v) not in ("0", "0.0", "False", ""):
                        parts.append(_KEY_NAMES.get(k, k))
                else:
                    unit = _UNITS.get(k, "")
                    parts.append(f"{_KEY_NAMES.get(k, k)} {v}{unit}".rstrip())
            detail = ", ".join(parts)
            lines.append(f"  {i}. {label}" + (f": {detail}" if detail else ""))
        try:
            size = len(R.encode(
                [R.Step(R.StepType(s["type"]), dict(s.get("values", {})))
                 for s in steps_raw]).encode("utf-8"))
            lines.append(f"  ({size} of {R.MAX_RECIPE_BYTES} bytes)")
        except Exception:                        # noqa: BLE001
            lines.append("  (could not size — check the steps)")
        lines.append("")
    return "\n".join(lines) + "\n"


def read_recipes(directory: str) -> tuple[list[dict], list[str]]:
    """Read every `*.json` back into records. Returns (records, errors).

    A single unreadable or malformed file is reported and skipped, never fatal:
    importing ten good recipes and naming the one bad file beats refusing the
    whole set because of a stray edit.
    """
    d = Path(directory)
    if not d.exists():
        return [], [f"{directory} does not exist"]
    records: list[dict] = []
    errors: list[str] = []
    for path in sorted(d.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as ex:
            errors.append(f"{path.name}: {ex}")
            continue
        from .library import record_from_any
        rec = record_from_any(data)
        if rec is None:
            errors.append(f"{path.name}: not a recipe (needs a name and steps)")
            continue
        records.append(rec)
    return records, errors

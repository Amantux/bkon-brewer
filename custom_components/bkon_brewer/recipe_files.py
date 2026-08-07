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
    for rec in records:
        name = (rec.get("name") or "").strip()
        if not name:
            continue
        fname = f"{_slug(name)}.json"
        keep.add(fname)
        payload = json.dumps(
            {"name": name, "steps": rec.get("steps", [])},
            indent=2, sort_keys=True, ensure_ascii=False) + "\n"
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
        if not isinstance(data, dict) or "name" not in data:
            errors.append(f"{path.name}: not a recipe (needs a name and steps)")
            continue
        records.append({"name": data.get("name"),
                        "steps": data.get("steps", [])})
    return records, errors

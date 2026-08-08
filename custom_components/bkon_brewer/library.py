"""Saved recipes. See docs/PROTOCOL.md for the step model.

A recipe is a named list of steps that survives restarts, so "create a recipe"
means something durable rather than a one-shot service call. Backed by Home
Assistant's Store; the steps are kept in the same {type, values} shape the
encoder consumes, so a saved recipe brews through exactly the same path as an
ad-hoc one.
"""
from __future__ import annotations

import logging
from typing import Any

from .const import DOMAIN
from .protocol import recipe as R

_LOGGER = logging.getLogger(__name__)

#: Journal entries kept per recipe. Bounded because the whole library rides on a
#: sensor's attributes, and an unbounded list there would bloat the state
#: machine and every recorder row that mentions it.
JOURNAL_MAX = 20

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.recipes"


def _slug(name: str) -> str:
    """Stable id for a recipe name. Names are for people; ids are for lookups."""
    return "".join(c if c.isalnum() else "_" for c in name.strip().lower()).strip("_")


class RecipeLibrary:
    """Load, list, save and delete named recipes."""

    def __init__(self, hass) -> None:
        from homeassistant.helpers.storage import Store
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._recipes: dict[str, dict[str, Any]] = {}
        self._loaded = False

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._recipes = data.get("recipes", {})
        self._loaded = True
        if not self._recipes:
            # Seed from the bundled default recipes so a fresh install opens on a
            # real starter set, not an empty screen. These ship with the
            # integration (defaults/) and are the same recipes checked into the
            # repo; the user edits, adds and exports from here.
            self._recipes = _load_defaults()
            await self.async_save()

    async def async_save(self) -> None:
        if self._loaded:
            await self._store.async_save({"recipes": self._recipes})

    def list(self) -> list[dict[str, Any]]:
        """Every saved recipe, with a rendered byte size against the limit.

        The size is computed here rather than stored, because it is derived from
        the steps and storing it would let the two drift. It is the single most
        useful number when building a recipe: how much BLE budget is left.
        """
        out = []
        for rid, rec in sorted(self._recipes.items()):
            steps = _to_steps(rec["steps"])
            try:
                size = len(R.encode(steps).encode("utf-8"))
                error = None
            except Exception as ex:                  # noqa: BLE001
                size, error = None, str(ex)
            out.append({
                "id": rid,
                "name": rec.get("name", rid),
                "steps": rec["steps"],
                "size_bytes": size,
                "max_bytes": R.MAX_RECIPE_BYTES,
                "error": error,
                "rating": rec.get("rating"),
                "notes": rec.get("notes", ""),
                # The tasting journal rides on the library sensor's attributes,
                # which is what makes it readable by MCP and any automation --
                # the studio's browser store alone was invisible to everything.
                "journal": rec.get("journal", []),
            })
        return out

    def get_record(self, id_or_name: str) -> dict | None:
        """The full stored record (name + raw steps) for one recipe, or None.

        The read half of CRUD: get() returns typed Steps for brewing; this
        returns the plain record for display, export, and round-tripping.
        """
        rec = self._recipes.get(id_or_name) or self._recipes.get(_slug(id_or_name))
        if rec is None:
            return None
        return {"id": _slug(rec.get("name", id_or_name)),
                "name": rec.get("name"), "steps": rec.get("steps", []),
                "description": rec.get("description", ""),
                "rating": rec.get("rating"), "notes": rec.get("notes", ""),
                "journal": rec.get("journal", [])}

    def get(self, id_or_name: str) -> list[R.Step] | None:
        rec = self._recipes.get(id_or_name) or self._recipes.get(_slug(id_or_name))
        if rec is None:
            return None
        return _to_steps(rec["steps"])

    async def async_put(self, name: str, steps: list[dict[str, Any]],
                        description: str = "") -> str:
        """Create or overwrite a recipe. Validated before it is stored.

        A recipe that cannot encode is rejected at save time, so the library
        never contains something that will only fail when you try to brew it.
        """
        R.validate(_to_steps(steps))              # raises before persisting
        rid = _slug(name)
        rec = {"name": name, "steps": steps}
        if description:
            rec["description"] = description
        # A save is about the steps; a rating and notes are the user's own
        # feedback and outlive an edit, so carry them across an overwrite.
        prev = self._recipes.get(rid)
        if prev:
            if prev.get("rating") is not None:
                rec["rating"] = prev["rating"]
            if prev.get("notes"):
                rec["notes"] = prev["notes"]
            if prev.get("journal"):
                rec["journal"] = prev["journal"]
        self._recipes[rid] = rec
        await self.async_save()
        return rid

    async def async_rate(self, id_or_name: str, rating: int | None = None,
                         notes: str | None = None) -> bool:
        """Attach the user's rating and notes to a recipe.

        `rating` 1-5 sets a rating, 0 clears it, None leaves it unchanged.
        `notes` sets the note when given, None leaves it unchanged. Feedback,
        not a recipe edit: the steps are untouched. Returns False if there is no
        such recipe.
        """
        rid = id_or_name if id_or_name in self._recipes else _slug(id_or_name)
        rec = self._recipes.get(rid)
        if rec is None:
            return False
        if rating is not None:
            if int(rating) <= 0:
                rec.pop("rating", None)
            else:
                rec["rating"] = max(1, min(5, int(rating)))
        if notes is not None:
            rec["notes"] = str(notes)
        self._recipes[rid] = rec
        await self.async_save()
        return True

    async def async_note(self, id_or_name: str, *, changes: list[str] | None = None,
                         taste: str = "", rating: int | None = None,
                         when: str = "") -> dict | None:
        """Append one tasting-journal entry: what changed, and how it tasted.

        The pairing is the point. The machine can know exactly what moved and can
        never know the flavour; you know the flavour and will not remember the
        numbers. Recorded together, they are the only basis for answering "what
        made it less bitter?". Returns the stored entry, or None if there is no
        such recipe.
        """
        rid = id_or_name if id_or_name in self._recipes else _slug(id_or_name)
        rec = self._recipes.get(rid)
        if rec is None:
            return None
        entry = {"when": when or "", "changes": list(changes or []),
                 "taste": str(taste or "")}
        if rating is not None:
            entry["rating"] = max(0, min(5, int(rating)))
        journal = list(rec.get("journal", []))
        journal.append(entry)
        rec["journal"] = journal[-JOURNAL_MAX:]
        self._recipes[rid] = rec
        await self.async_save()
        return entry

    async def async_delete(self, id_or_name: str) -> bool:
        rid = id_or_name if id_or_name in self._recipes else _slug(id_or_name)
        if rid in self._recipes:
            del self._recipes[rid]
            await self.async_save()
            return True
        return False

    # -- git-friendly export / import ------------------------------------
    # HA's .storage JSON is one opaque blob -- terrible to diff or review in a
    # pull request. Export writes one file per recipe, stable-keyed and sorted,
    # so a change to one recipe is a one-file diff a human can read.

    def export_dict(self) -> dict:
        """The whole library as an ordered, JSON/YAML-round-trippable dict.

        Empty feedback fields are pruned so a recipe nobody has rated exports
        byte-for-byte as before -- rating and notes only appear once set.
        """
        records = []
        for rid in sorted(self._recipes):
            rec = self.get_record(rid)
            if rec.get("rating") is None:
                rec.pop("rating", None)
            if not rec.get("notes"):
                rec.pop("notes", None)
            if not rec.get("journal"):
                rec.pop("journal", None)
            records.append(rec)
        return {"version": 1, "recipes": records}

    async def async_import_records(self, records: list[dict],
                                   replace: bool = False) -> dict:
        """Upsert recipes from exported records. Returns a small change report.

        Each record is validated before it lands, so a malformed file cannot
        poison the library -- a bad recipe is skipped and reported, the good
        ones still import. `replace` clears first (a mirror of the files);
        otherwise it is an upsert (files win on a name clash).
        """
        added = updated = skipped = 0
        errors: list[str] = []
        if replace:
            self._recipes = {}
        for rec in records:
            name = (rec.get("name") or "").strip()
            steps = rec.get("steps")
            if not name or not isinstance(steps, list):
                skipped += 1
                errors.append(f"{name or '(unnamed)'}: missing name or steps")
                continue
            try:
                R.validate(_to_steps(steps))          # reject before storing
            except Exception as ex:                   # noqa: BLE001
                skipped += 1
                errors.append(f"{name}: {ex}")
                continue
            rid = _slug(name)
            if rid in self._recipes:
                updated += 1
            else:
                added += 1
            rec_out = {"name": name, "steps": steps}
            if rec.get("description"):
                rec_out["description"] = rec["description"]
            if rec.get("rating") is not None:
                rec_out["rating"] = rec["rating"]
            if rec.get("notes"):
                rec_out["notes"] = rec["notes"]
            if rec.get("journal"):
                rec_out["journal"] = list(rec["journal"])[-JOURNAL_MAX:]
            self._recipes[rid] = rec_out
        await self.async_save()
        return {"added": added, "updated": updated, "skipped": skipped,
                "errors": errors}


def _to_steps(raw: list[dict[str, Any]]) -> list[R.Step]:
    return [R.Step(R.StepType(s["type"]), dict(s.get("values", {}))) for s in raw]


def _load_defaults() -> dict[str, dict[str, Any]]:
    """Read the bundled default recipes into the library's flat form.

    The default files are in the app's recipe-object schema (see app_recipe);
    the first portion becomes the library's steps. Falls back to the built-in
    example if the directory is missing, so a fresh install is never empty."""
    import json
    from pathlib import Path
    from . import app_recipe
    out: dict[str, dict[str, Any]] = {}
    d = Path(__file__).parent / "defaults"
    if d.exists():
        for f in sorted(d.glob("*.json")):
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            rec = record_from_any(obj)
            if rec:
                out[_slug(rec["name"])] = rec
    return out or {"example_pour_over": _EXAMPLE}


def record_from_any(obj: dict) -> dict[str, Any] | None:
    """Coerce a stored object -- app-schema or our flat form -- into a library
    record {name, steps, description}. One reader for both shapes so a file can
    be either, and a hand-authored app recipe imports the same as a flat one."""
    from . import app_recipe
    if app_recipe.is_app_recipe(obj):
        name, steps = app_recipe.from_app_recipe(obj)
        rec = {"name": name, "steps": steps}
        if obj.get("description"):
            rec["description"] = obj["description"]
        return rec
    name = obj.get("name")
    if name and isinstance(obj.get("steps"), list):
        rec = {"name": name, "steps": obj["steps"]}
        if obj.get("description"):
            rec["description"] = obj["description"]
        return rec
    return None


_EXAMPLE: dict[str, Any] = {
    "name": "Example Pour Over",
    "steps": [
        {"type": "start", "values": {"tmp": 205}},
        {"type": "fr", "values": {"fwv": 250, "rwv": 30}},
        {"type": "dialog", "values": {"text": "Add grounds and press start"}},
        {"type": "vc", "values": {"ps": 50, "tm": 30}},
        {"type": "pg", "values": {"ps": 50, "tm": 10, "det": 1}},
    ],
}

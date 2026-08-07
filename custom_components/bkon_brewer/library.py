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
            # Seed one editable example so the library is never an empty screen.
            # It is a real, valid recipe, not a placeholder -- brewing it does
            # something sensible, and editing it teaches the shape.
            self._recipes = {"example_pour_over": _EXAMPLE}
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
            })
        return out

    def get(self, id_or_name: str) -> list[R.Step] | None:
        rec = self._recipes.get(id_or_name) or self._recipes.get(_slug(id_or_name))
        if rec is None:
            return None
        return _to_steps(rec["steps"])

    async def async_put(self, name: str, steps: list[dict[str, Any]]) -> str:
        """Create or overwrite a recipe. Validated before it is stored.

        A recipe that cannot encode is rejected at save time, so the library
        never contains something that will only fail when you try to brew it.
        """
        R.validate(_to_steps(steps))              # raises before persisting
        rid = _slug(name)
        self._recipes[rid] = {"name": name, "steps": steps}
        await self.async_save()
        return rid

    async def async_delete(self, id_or_name: str) -> bool:
        rid = id_or_name if id_or_name in self._recipes else _slug(id_or_name)
        if rid in self._recipes:
            del self._recipes[rid]
            await self.async_save()
            return True
        return False


def _to_steps(raw: list[dict[str, Any]]) -> list[R.Step]:
    return [R.Step(R.StepType(s["type"]), dict(s.get("values", {}))) for s in raw]


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

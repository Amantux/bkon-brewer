"""The BKON app's recipe object shape, and conversion to/from our flat steps.

Recovered from the app's own menu data (testMenus.json). A recipe as the app
stores it is not a flat list of steps -- it is a rich object:

    recipe: id, name, dsp_name, description, notes, status, code, image,
            date, modified,
            sequences: { portions: [ { name, sequences: [ step, ... ] } ] }
    step:   { type, values }

with named portions ("small" / "medium" / "large") each carrying their own
steps, so one recipe holds several serving sizes. Our internal model is one
portion's flat steps -- what the BLE encoder sends -- so this module converts
between the two.

Two key-name facts the app data settles, both of which our earlier flat model
had wrong:

  * A **fill's** atmospheric pause is `ap`, not `dl`. (`dl` is the *purge*
    delay.) The FillEditor and the stored menus agree.
  * A **purge** stores detection and control as `purgedet` / `purgecontr` in the
    menu format, but the editor and the BLE wire use `det` / `contr`. So the
    on-disk app form and the wire form differ by exactly these two keys, and
    conversion has to alias them or a purge silently loses its flags.
"""
from __future__ import annotations

from typing import Any

# Menu-storage key  <->  editor/wire key. Only the purge flags differ.
_STORAGE_TO_WIRE = {"purgedet": "det", "purgecontr": "contr"}
_WIRE_TO_STORAGE = {v: k for k, v in _STORAGE_TO_WIRE.items()}

DEFAULT_PORTION = "standard"


def _to_wire(values: dict) -> dict:
    return {_STORAGE_TO_WIRE.get(k, k): v for k, v in (values or {}).items()}


def _to_storage(values: dict) -> dict:
    return {_WIRE_TO_STORAGE.get(k, k): v for k, v in (values or {}).items()}


def portions_of(recipe: dict) -> list[str]:
    """The portion names on an app recipe, in order."""
    return [p.get("name", "")
            for p in recipe.get("sequences", {}).get("portions", [])]


def from_app_recipe(recipe: dict, portion: str | None = None
                    ) -> tuple[str, list[dict]]:
    """(display name, flat wire-key steps) for one portion of an app recipe.

    Picks the named portion, else the first. Steps come back in wire-key form
    (purgedet -> det) so the encoder and the rest of the integration see the
    keys they already expect.
    """
    name = recipe.get("dsp_name") or recipe.get("name") or "Recipe"
    portions = recipe.get("sequences", {}).get("portions", [])
    chosen = None
    if portion:
        chosen = next((p for p in portions if p.get("name") == portion), None)
    if chosen is None:
        chosen = portions[0] if portions else {"sequences": []}
    steps = [{"type": s.get("type"), "values": _to_wire(s.get("values", {}))}
             for s in chosen.get("sequences", [])]
    return name, steps


def to_app_recipe(name: str, portions: list[tuple[str, list[dict]]], *,
                  description: str = "", notes: str = "") -> dict:
    """Build an app-shaped recipe object from named (portion, flat-steps) pairs.

    Emits the app's storage key names (det -> purgedet), so a file written here
    is the same shape the app itself produces and could be re-imported into it.
    Metadata the app carries but we do not use is set to sensible blanks rather
    than omitted, so the object matches the app's schema exactly.
    """
    out_portions = []
    for pname, steps in portions:
        seqs = [{"type": s.get("type"),
                 "values": _to_storage(s.get("values", {}))}
                for s in steps]
        out_portions.append({"name": pname, "sequences": seqs})
    return {
        "name": name,
        "dsp_name": name,
        "description": description,
        "notes": notes,
        "status": "1",
        "code": "",
        "image": "",
        "sequences": {"portions": out_portions},
    }


def to_menu(description: str, recipes: list[dict], *,
            category: str = "Home Assistant") -> dict:
    """Wrap app-schema recipe objects into a full menu object.

    The device holds an on-board MENU (menu -> category -> recipe), loaded as a
    file via the Service Menu's "Update Recipe File" from USB -- a path with no
    Bluetooth 599-byte limit, because it is a file, not a characteristic write.
    This builds that menu object so the integration can produce a loadable file
    for longer recipes than BLE allows.

    The exact on-USB folder layout the Service Menu expects is not fully
    confirmed from the recovered material (see docs/LONGER_RECIPES.md); this
    produces the recipe/menu OBJECT shape the app itself uses, which is the
    payload inside that layout.
    """
    return {
        "description": description,
        "config": "n",
        "recipes": [{
            "color": "#00ff00",
            "name": category,
            "recipes": recipes,
        }],
    }


def is_app_recipe(obj: dict) -> bool:
    """Does this look like an app recipe object (vs our flat {name, steps})?"""
    return isinstance(obj, dict) and "sequences" in obj \
        and isinstance(obj.get("sequences"), dict) \
        and "portions" in obj["sequences"]

"""BKON Craft Brewer integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .const import (
    SIGNAL_EVENT, CONF_ADDRESS, CONF_KB_PATH, CONF_SIMULATE, DEFAULT_KB_FILENAME, DOMAIN,
    SERVICE_ABORT, SERVICE_ASK, SERVICE_BREW, SERVICE_BREW_SAVED,
    SERVICE_CUSTOMIZE, SERVICE_DELETE_RECIPE, SERVICE_MANUAL_PURGE,
    SERVICE_RATE_RECIPE, SERVICE_RESPOND_DIALOG, SERVICE_SAVE_RECIPE, SERVICE_SEND_RAW,
    SERVICE_LINT, SERVICE_DIAGNOSE, SERVICE_BUILD,
    SERVICE_GET, SERVICE_EXPORT, SERVICE_IMPORT, SERVICE_DOWNLOAD,
    SERVICE_EXPORT_MENU, DEFAULT_RECIPE_DIR,
    CONF_LIGHTRAG_URL, CONF_LIGHTRAG_KEY, CONF_RAG_MODE)
from . import advisor, app_recipe, concierge, diagnostics, rag_backend, recipe_files, templates, tools
from .coordinator import BrewerCoordinator
from .knowledge import KnowledgeBase
from .library import RecipeLibrary
from .protocol import recipe as R
from .transport import BrewerUnavailable

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.CONVERSATION]

# A recipe passed to the brew service: a list of {type, values} dicts, the same
# shape the protocol layer consumes. Kept permissive here and validated for real
# by the encoder, which owns the rules.
_STEP_SCHEMA = vol.Schema({
    vol.Required("type"): cv.string,
    vol.Optional("values", default={}): dict,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    coordinator = BrewerCoordinator(
        hass, address, entry.title,
        simulate=entry.data.get(CONF_SIMULATE, False))

    try:
        await coordinator.async_start()
    except BrewerUnavailable as ex:
        # Not ready, not failed: the brewer may simply be out of range or off.
        # ConfigEntryNotReady makes Home Assistant retry rather than mark the
        # integration broken, which matches a battery/BLE device that comes and
        # goes.
        raise ConfigEntryNotReady(str(ex)) from ex

    store = hass.data.setdefault(DOMAIN, {})
    if "library" not in store:
        library = RecipeLibrary(hass)
        await library.async_load()
        store["library"] = library
    if "kb" not in store:
        # The index lives in the config dir by default. Absent is fine -- the
        # concierge just says questions are unavailable until it is built.
        kb_path = entry.data.get(CONF_KB_PATH) or hass.config.path(
            DEFAULT_KB_FILENAME)
        store["kb"] = await hass.async_add_executor_job(
            KnowledgeBase.from_file, kb_path)
    # Optional LightRAG upgrade. Rebuilt on every setup so options edits take
    # effect on reload; absent URL means the local retriever is the whole story.
    opts = {**entry.data, **entry.options}
    url = opts.get(CONF_LIGHTRAG_URL)
    store["rag"] = (
        rag_backend.LightRagBackend(
            url, api_key=opts.get(CONF_LIGHTRAG_KEY),
            mode=opts.get(CONF_RAG_MODE, rag_backend.DEFAULT_MODE))
        if url else None)
    store[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: BrewerCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unloaded


def _notify_library_changed(hass: HomeAssistant) -> None:
    """Nudge entities to re-read the library after a save or delete.

    The library sensor is push-based like everything else here, so a change made
    through a service (not the brewer) needs an explicit signal or the UI keeps
    showing the old count until the next brewer event.
    """
    from .protocol.events import BrewerEvent, EventType
    for c in hass.data.get(DOMAIN, {}).values():
        if isinstance(c, BrewerCoordinator):
            async_dispatcher_send(
                hass, f"{SIGNAL_EVENT}_{c.address}",
                BrewerEvent(EventType.UNKNOWN, raw="library:changed"))


def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[BrewerCoordinator]:
    """Resolve which brewer(s) a service call targets.

    With a single brewer the target is unambiguous and may be omitted. This
    stays correct if a second brewer is ever added rather than silently acting
    on the wrong one.
    """
    store: dict = hass.data.get(DOMAIN, {})
    wanted = call.data.get("address")
    out = [c for c in store.values()
           if isinstance(c, BrewerCoordinator) and wanted in (None, c.address)]
    if not out:
        raise vol.Invalid(f"No BKON brewer matching {wanted!r}")
    return out


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ABORT):
        return

    async def _brew(call: ServiceCall) -> None:
        raw_steps = call.data["steps"]
        steps = [R.Step(R.StepType(s["type"]), dict(s.get("values", {})))
                 for s in raw_steps]
        for c in _coordinators(hass, call):
            await c.async_brew(steps)

    async def _manual_purge(call: ServiceCall) -> None:
        for c in _coordinators(hass, call):
            await c.async_manual_purge(
                pressure=call.data.get("pressure", 50),
                time=call.data.get("time", 10),
                detect=call.data.get("detect", False))

    async def _abort(call: ServiceCall) -> None:
        for c in _coordinators(hass, call):
            await c.async_abort()

    async def _respond(call: ServiceCall) -> None:
        for c in _coordinators(hass, call):
            await c.async_respond_dialog(int(call.data["button"]))

    async def _send_raw(call: ServiceCall) -> None:
        for c in _coordinators(hass, call):
            await c.async_send_raw(call.data["payload"])

    hass.services.async_register(
        DOMAIN, SERVICE_BREW, _brew,
        schema=vol.Schema({
            vol.Optional("address"): cv.string,
            vol.Required("steps"): [_STEP_SCHEMA],
        }))
    hass.services.async_register(
        DOMAIN, SERVICE_MANUAL_PURGE, _manual_purge,
        schema=vol.Schema({
            vol.Optional("address"): cv.string,
            vol.Optional("pressure", default=50): vol.Coerce(int),
            vol.Optional("time", default=10): vol.Coerce(int),
            vol.Optional("detect", default=False): cv.boolean,
        }))
    hass.services.async_register(
        DOMAIN, SERVICE_ABORT, _abort,
        schema=vol.Schema({vol.Optional("address"): cv.string}))
    hass.services.async_register(
        DOMAIN, SERVICE_RESPOND_DIALOG, _respond,
        schema=vol.Schema({
            vol.Optional("address"): cv.string,
            vol.Required("button"): vol.Coerce(int),
        }))
    async def _ask(call: ServiceCall) -> dict:
        """Answer a question or preview a recipe tweak. Returns response data."""
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        kb: KnowledgeBase = hass.data[DOMAIN].get("kb")
        recipes = {r["name"]: library.get(r["id"]) for r in library.list()}
        reply = concierge.respond(call.data["message"], recipes, kb)
        if reply.kind == "answer" and not reply.composed:
            session = async_get_clientsession(hass)
            text, src = await rag_backend.answer_with_fallback(
                session, hass.data[DOMAIN].get("rag"), kb, call.data["message"])
            reply.text = text
            out = {"kind": reply.kind, "response": text, "source": src}
        else:
            out = {"kind": reply.kind, "response": reply.text}
        if reply.new_steps is not None:
            out["recipe"] = reply.recipe_name
            out["steps"] = [{"type": str(st.type), "values": st.values}
                            for st in reply.new_steps]
        return out

    async def _customize(call: ServiceCall) -> dict:
        """Apply feedback to a saved recipe; optionally save the result."""
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        name = call.data["name"]
        steps = library.get(name)
        if steps is None:
            raise vol.Invalid(f"No saved recipe named {name!r}")
        result = advisor.customize(steps, call.data["feedback"])
        out = {
            "changed": result.changed,
            "summary": result.summary(),
            "steps": [{"type": str(st.type), "values": st.values}
                      for st in result.steps],
        }
        save_as = call.data.get("save_as")
        if save_as and result.changed:
            raw = [{"type": str(st.type), "values": st.values}
                   for st in result.steps]
            out["saved_as"] = await library.async_put(save_as, raw)
            _notify_library_changed(hass)
        return out

    async def _lint(call: ServiceCall) -> dict:
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        recipes = {r["name"]: library.get(r["id"]) for r in library.list()}
        return tools.execute_tool(
            "lint_recipe", {"name": call.data["name"]}, recipes=recipes)

    async def _diagnose(call: ServiceCall) -> dict:
        kb = hass.data[DOMAIN].get("kb")
        return tools.execute_tool("diagnose", {"text": call.data["text"]}, kb=kb)

    async def _build(call: ServiceCall) -> dict:
        out = tools.execute_tool(
            "build_recipe", {"description": call.data["description"]})
        save_as = call.data.get("save_as")
        if save_as and "steps" in out:
            library: RecipeLibrary = hass.data[DOMAIN]["library"]
            out["saved_as"] = await library.async_put(save_as, out["steps"])
            _notify_library_changed(hass)
        return out

    def _recipe_dir(call: ServiceCall) -> str:
        # Default under the config dir so it is on the same volume and easy to
        # git-init; an absolute path in the call overrides it.
        d = call.data.get("directory")
        return d if d else hass.config.path(DEFAULT_RECIPE_DIR)

    async def _get_recipe(call: ServiceCall) -> dict:
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        rec = library.get_record(call.data["name"])
        if rec is None:
            return {"found": False, "error": f"no recipe named {call.data['name']!r}"}
        steps = library.get(rec["id"])
        problems = tools.execute_tool("lint_recipe", {"name": rec["id"]},
                                      recipes={rec["id"]: steps})
        return {"found": True, **rec, "ok": problems.get("ok"),
                "problems": problems.get("problems", [])}

    async def _export(call: ServiceCall) -> dict:
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        records = library.export_dict()["recipes"]
        directory = _recipe_dir(call)
        report = await hass.async_add_executor_job(
            recipe_files.write_recipes, directory, records)
        return report

    async def _import(call: ServiceCall) -> dict:
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        directory = _recipe_dir(call)
        records, read_errors = await hass.async_add_executor_job(
            recipe_files.read_recipes, directory)
        report = await library.async_import_records(
            records, replace=call.data.get("replace", False))
        _notify_library_changed(hass)
        report["read_errors"] = read_errors
        return report

    async def _download(call: ServiceCall) -> dict:
        """Write a readable recipes .txt to /config/www for download.

        Home Assistant serves /config/www at /local, so the file is reachable in
        a browser without any extra server. Returns the path and the URL.
        """
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        records = library.export_dict()["recipes"]
        text = recipe_files.to_text(records)
        www = hass.config.path("www", "bkon")
        fname = call.data.get("filename", "bkon_recipes.txt")

        def _write() -> str:
            import os
            os.makedirs(www, exist_ok=True)
            path = os.path.join(www, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return path

        path = await hass.async_add_executor_job(_write)
        return {"path": path, "url": f"/local/bkon/{fname}",
                "recipes": len(records), "bytes": len(text)}

    async def _export_menu(call: ServiceCall) -> dict:
        """Write all recipes as one device-style MENU file to /config/www.

        The Service Menu's USB "Update Recipe File" path loads a menu file with
        no Bluetooth 599-byte limit, so this is the route to longer recipes than
        BLE allows. Each recipe is emitted with all its portions.
        """
        import json as _json
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        recipes = []
        for r in library.list():
            steps = library.get(r["id"])
            recipes.append(app_recipe.to_app_recipe(
                r["name"], [(app_recipe.DEFAULT_PORTION,
                             [{"type": str(s.type), "values": s.values}
                              for s in steps])],
                description=r.get("description", "")))
        menu = app_recipe.to_menu(
            call.data.get("menu_name", "Home Assistant Menu"), recipes)
        www = hass.config.path("www", "bkon")
        fname = call.data.get("filename", "bkon_menu.json")

        def _write() -> str:
            import os
            os.makedirs(www, exist_ok=True)
            path = os.path.join(www, fname)
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(menu, f, indent=2, ensure_ascii=False)
            return path

        path = await hass.async_add_executor_job(_write)
        return {"path": path, "url": f"/local/bkon/{fname}",
                "recipes": len(recipes),
                "note": "Load via the machine's Service Menu > Update Recipe "
                        "File (USB). Not limited to 599 bytes like a BLE brew."}

    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_MENU, _export_menu,
        schema=vol.Schema({
            vol.Optional("menu_name"): cv.string,
            vol.Optional("filename"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)

    hass.services.async_register(
        DOMAIN, SERVICE_DOWNLOAD, _download,
        schema=vol.Schema({vol.Optional("filename"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)

    hass.services.async_register(
        DOMAIN, SERVICE_GET, _get_recipe,
        schema=vol.Schema({vol.Required("name"): cv.string}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT, _export,
        schema=vol.Schema({vol.Optional("directory"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT, _import,
        schema=vol.Schema({
            vol.Optional("directory"): cv.string,
            vol.Optional("replace", default=False): cv.boolean}),
        supports_response=SupportsResponse.OPTIONAL)

    hass.services.async_register(
        DOMAIN, SERVICE_LINT, _lint,
        schema=vol.Schema({vol.Required("name"): cv.string}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(
        DOMAIN, SERVICE_DIAGNOSE, _diagnose,
        schema=vol.Schema({vol.Required("text"): cv.string}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(
        DOMAIN, SERVICE_BUILD, _build,
        schema=vol.Schema({
            vol.Required("description"): cv.string,
            vol.Optional("save_as"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)

    hass.services.async_register(
        DOMAIN, SERVICE_ASK, _ask,
        schema=vol.Schema({vol.Required("message"): cv.string}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(
        DOMAIN, SERVICE_CUSTOMIZE, _customize,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Required("feedback"): cv.string,
            vol.Optional("save_as"): cv.string,
        }),
        supports_response=SupportsResponse.OPTIONAL)

    async def _save_recipe(call: ServiceCall) -> None:
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        await library.async_put(call.data["name"], call.data["steps"])
        # A rating/notes may ride along with a save from the studio.
        if "rating" in call.data or "notes" in call.data:
            await library.async_rate(call.data["name"],
                                     rating=call.data.get("rating"),
                                     notes=call.data.get("notes"))
        _notify_library_changed(hass)

    async def _rate_recipe(call: ServiceCall) -> dict:
        """Save the user's rating (1-5, 0 clears) and/or notes for a recipe."""
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        ok = await library.async_rate(call.data["name"],
                                      rating=call.data.get("rating"),
                                      notes=call.data.get("notes"))
        if not ok:
            raise vol.Invalid(f"No saved recipe named {call.data['name']!r}")
        _notify_library_changed(hass)
        rec = library.get_record(call.data["name"])
        return {"name": rec["name"], "rating": rec.get("rating"),
                "notes": rec.get("notes", "")}

    async def _delete_recipe(call: ServiceCall) -> None:
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        await library.async_delete(call.data["name"])
        _notify_library_changed(hass)

    async def _brew_saved(call: ServiceCall) -> None:
        library: RecipeLibrary = hass.data[DOMAIN]["library"]
        steps = library.get(call.data["name"])
        if steps is None:
            raise vol.Invalid(f"No saved recipe named {call.data['name']!r}")
        for c in _coordinators(hass, call):
            await c.async_brew(steps)

    hass.services.async_register(
        DOMAIN, SERVICE_SAVE_RECIPE, _save_recipe,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Required("steps"): [_STEP_SCHEMA],
            vol.Optional("rating"): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Optional("notes"): cv.string,
        }))
    hass.services.async_register(
        DOMAIN, SERVICE_RATE_RECIPE, _rate_recipe,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Optional("rating"): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Optional("notes"): cv.string,
        }),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_RECIPE, _delete_recipe,
        schema=vol.Schema({vol.Required("name"): cv.string}))
    hass.services.async_register(
        DOMAIN, SERVICE_BREW_SAVED, _brew_saved,
        schema=vol.Schema({
            vol.Optional("address"): cv.string,
            vol.Required("name"): cv.string,
        }))

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_RAW, _send_raw,
        schema=vol.Schema({
            vol.Optional("address"): cv.string,
            vol.Required("payload"): cv.string,
        }))

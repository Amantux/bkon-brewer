"""BKON Craft Brewer integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .const import (
    SIGNAL_EVENT, CONF_ADDRESS, CONF_KB_PATH, CONF_SIMULATE, DEFAULT_KB_FILENAME, DOMAIN,
    SERVICE_ABORT, SERVICE_ASK, SERVICE_BREW, SERVICE_BREW_SAVED,
    SERVICE_CUSTOMIZE, SERVICE_DELETE_RECIPE, SERVICE_MANUAL_PURGE,
    SERVICE_RESPOND_DIALOG, SERVICE_SAVE_RECIPE, SERVICE_SEND_RAW)
from . import advisor, concierge
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
        _notify_library_changed(hass)

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
        }))
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

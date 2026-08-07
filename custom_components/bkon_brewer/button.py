"""Buttons: the two actions you want reachable in one tap."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import BrewerCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities) -> None:
    c: BrewerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AbortButton(c), ManualPurgeButton(c)])


class _Base(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, c: BrewerCoordinator) -> None:
        self._c = c
        self._attr_device_info = {
            "identifiers": {(DOMAIN, c.address)},
            "name": c.name,
            "manufacturer": "BKON",
            "model": "Craft Brewer",
        }


class AbortButton(_Base):
    _attr_name = "Abort"
    _attr_icon = "mdi:stop-circle-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._c.address}_abort"

    async def async_press(self) -> None:
        await self._c.async_abort()


class ManualPurgeButton(_Base):
    """A one-tap purge with the app's own default parameters.

    Anything more configurable belongs in the manual_purge service; this is the
    common case -- clear the chamber -- made reachable without composing a
    service call.
    """

    _attr_name = "Manual purge"
    _attr_icon = "mdi:air-filter"

    @property
    def unique_id(self) -> str:
        return f"{self._c.address}_purge"

    async def async_press(self) -> None:
        await self._c.async_manual_purge()

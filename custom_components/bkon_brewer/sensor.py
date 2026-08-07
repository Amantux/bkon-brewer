"""Sensors: what the brewer is doing, and its last words."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, SIGNAL_EVENT
from .coordinator import BrewerCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities) -> None:
    c: BrewerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        StatusSensor(c, entry), StepSensor(c, entry),
        DialogSensor(c, entry), ErrorSensor(c, entry),
    ])


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, c: BrewerCoordinator, entry: ConfigEntry) -> None:
        self._c = c
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, c.address)},
            "name": c.name,
            "manufacturer": "BKON",
            "model": "Craft Brewer",
        }

    async def async_added_to_hass(self) -> None:
        # local_push: state changes arrive as dispatcher signals, so each entity
        # just re-reads the coordinator and writes itself out. No polling.
        self.async_on_remove(async_dispatcher_connect(
            self.hass, f"{SIGNAL_EVENT}_{self._c.address}", self._updated))

    @callback
    def _updated(self, _event) -> None:
        self.async_write_ha_state()


class StatusSensor(_Base):
    _attr_name = "Status"
    _attr_icon = "mdi:coffee-maker"

    @property
    def unique_id(self) -> str:
        return f"{self._c.address}_status"

    @property
    def native_value(self) -> str:
        return self._c.status


class StepSensor(_Base):
    _attr_name = "Current step"
    _attr_icon = "mdi:format-list-numbered"

    @property
    def unique_id(self) -> str:
        return f"{self._c.address}_step"

    @property
    def native_value(self) -> int:
        return self._c.current_step


class DialogSensor(_Base):
    """The brewer's last prompt, so an automation can answer it."""

    _attr_name = "Dialog"
    _attr_icon = "mdi:message-question-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._c.address}_dialog"

    @property
    def native_value(self) -> str | None:
        # None, not empty string, when there is no outstanding prompt: an
        # automation can then trigger cleanly on "is not none".
        return self._c.last_dialog


class ErrorSensor(_Base):
    _attr_name = "Last error"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"{self._c.address}_error"

    @property
    def native_value(self) -> str | None:
        return self._c.last_error

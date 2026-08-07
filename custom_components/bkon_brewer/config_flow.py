"""Config flow: Bluetooth discovery, plus manual address entry."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADDRESS, CONF_LIGHTRAG_KEY, CONF_LIGHTRAG_URL, CONF_RAG_MODE,
    CONF_SIMULATE, DOMAIN)


class BkonBrewerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """A brewer advertised the Nordic UART service and HA found it."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovered = discovery_info
        # Show the name in the confirmation step rather than a bare MAC.
        self.context["title_placeholders"] = {
            "name": discovery_info.name or "BKON Brewer"
        }
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered.name or "BKON Brewer",
                data={CONF_ADDRESS: self._discovered.address})
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovered.name or "BKON Brewer",
                "address": self._discovered.address,
            })

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual entry, for when discovery has not fired yet.

        Nordic UART is a generic service, so we do not auto-add every device
        that advertises it -- the user picks. A discovery match narrows the
        list, but the final say is theirs.
        """
        if user_input is not None:
            simulate = user_input.get(CONF_SIMULATE, False)
            # A demo entry needs a unique id too, but its own -- so it can coexist
            # with a real brewer added later rather than colliding on address.
            address = "DEMO" if simulate else user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            title = "BKON Brewer (demo)" if simulate else "BKON Brewer"
            return self.async_create_entry(
                title=title,
                data={CONF_ADDRESS: address, CONF_SIMULATE: simulate})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional(CONF_ADDRESS, default=""): selector.TextSelector(),
                vol.Optional(CONF_SIMULATE, default=False): selector.BooleanSelector(),
            }),
            description_placeholders={
                "hint": "Enter the brewer's Bluetooth MAC, or tick Simulate to "
                        "explore the interface with no hardware."
            })

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> "BkonOptionsFlow":
        return BkonOptionsFlow()


class BkonOptionsFlow(OptionsFlow):
    """Configure the LightRAG upgrade. Leave the URL blank to use the built-in
    local retriever, which needs no server and no model."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            # An empty URL clears the upgrade rather than storing "".
            cleaned = {k: v for k, v in user_input.items() if v not in ("", None)}
            return self.async_create_entry(title="", data=cleaned)
        cur = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_LIGHTRAG_URL,
                             default=cur.get(CONF_LIGHTRAG_URL, "")): selector.TextSelector(),
                vol.Optional(CONF_LIGHTRAG_KEY,
                             default=cur.get(CONF_LIGHTRAG_KEY, "")): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
                vol.Optional(CONF_RAG_MODE,
                             default=cur.get(CONF_RAG_MODE, "hybrid")): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["hybrid", "local", "global", "mix", "naive"],
                        mode=selector.SelectSelectorMode.DROPDOWN)),
            }),
            description_placeholders={
                "hint": "Point this at your LightRAG server (e.g. "
                        "http://homeassistant.local:9621). The API key is the "
                        "one you set on the server."})

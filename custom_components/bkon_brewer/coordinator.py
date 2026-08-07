"""Connection lifecycle and brew state. See docs/PROTOCOL.md.

Owns the transport, turns the brewer's event stream into a status the rest of
Home Assistant can read, and exposes the actions (brew, purge, abort, answer a
dialog). Kept separate from the entities so the state machine can be reasoned
about on its own.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN, SIGNAL_EVENT, STATUS_BREWING, STATUS_COMPLETE, STATUS_DISCONNECTED,
    STATUS_ERROR, STATUS_IDLE, STATUS_WAITING)
from .protocol import recipe as R
from .protocol.events import BrewerEvent, EventType, parse_event
from .transport import BrewerTransport, BrewerUnavailable

_LOGGER = logging.getLogger(__name__)


class BrewerCoordinator:
    """One brewer: its link, its status, and the things you can ask it to do."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.status = STATUS_DISCONNECTED
        self.current_step = 0
        self.last_dialog: str | None = None
        self.last_error: str | None = None
        self.last_event_at: datetime | None = None
        self._transport = BrewerTransport(address, self._on_line)

    @property
    def connected(self) -> bool:
        return self._transport.connected

    async def async_start(self) -> None:
        await self._transport.async_connect(self.hass)
        self._set_status(STATUS_IDLE)

    async def async_stop(self) -> None:
        await self._transport.async_disconnect()
        self._set_status(STATUS_DISCONNECTED)

    # -- actions ----------------------------------------------------------

    async def async_brew(self, steps: list[R.Step]) -> None:
        """Validate, frame and send a recipe.

        Validation happens before anything touches the radio, so an oversized
        or malformed recipe fails loudly at the call site rather than half-way
        through a write with the brewer left in an unknown state.
        """
        payload = R.validate(steps)               # raises RecipeTooLarge early
        self.current_step = 0
        self.last_error = None
        await self._transport.async_send(R.frame(payload))
        self._set_status(STATUS_BREWING)

    async def async_manual_purge(self, pressure: int = 50, time: int = 10,
                                 detect: bool = False) -> None:
        cmd = R.encode_command(R.purge(pressure, time, detect=detect))
        await self._transport.async_send(R.frame(cmd))
        self._set_status(STATUS_BREWING)

    async def async_abort(self) -> None:
        await self._transport.async_send(R.ABORT)
        self._set_status(STATUS_IDLE)

    async def async_respond_dialog(self, button: int) -> None:
        """Answer a brewer prompt. Button 0 is cancel and ends the brew.

        Sent as a framed dialog response. The exact wire form of a dialog
        answer is one of the unverified items in docs/PROTOCOL.md -- the app
        calls a native `dialogResponse(n)` whose payload we have not captured --
        so this is a best-effort shape until hardware confirms it.
        """
        await self._transport.async_send(R.frame(f"<DIALOG>{button}</DIALOG>"))
        self.last_dialog = None
        if button == 0:
            self._set_status(STATUS_IDLE)
        else:
            self._set_status(STATUS_BREWING)

    async def async_send_raw(self, payload: str) -> None:
        """Escape hatch for protocol work: send an already-framed string."""
        await self._transport.async_send(payload)

    # -- event handling ---------------------------------------------------

    def _on_line(self, line: str) -> None:
        event = parse_event(line)
        self.last_event_at = datetime.now(timezone.utc)
        _LOGGER.debug("brewer %s event: %s", self.address, event)

        if event.type == EventType.STEP_COMPLETED:
            self.current_step += 1
        elif event.type == EventType.RECIPE_COMPLETED:
            self._set_status(STATUS_COMPLETE)
        elif event.type == EventType.DIALOG:
            self.last_dialog = event.text
            self._set_status(STATUS_WAITING)
        elif event.type == EventType.ERROR:
            self.last_error = event.text
            self._set_status(STATUS_ERROR)
        elif event.type == EventType.DISCONNECTED:
            self._set_status(STATUS_DISCONNECTED)

        # Entities listen on the dispatcher so a notification updates state the
        # instant it arrives -- this is a local_push device, not a polled one.
        async_dispatcher_send(self.hass, f"{SIGNAL_EVENT}_{self.address}", event)

    def _set_status(self, status: str) -> None:
        self.status = status
        async_dispatcher_send(
            self.hass, f"{SIGNAL_EVENT}_{self.address}",
            BrewerEvent(EventType.UNKNOWN, raw=f"status:{status}"))

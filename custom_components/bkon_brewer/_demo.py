"""A simulated brewer, so the UI can be exercised with no hardware.

This is not a mock in the testing sense — it is a stand-in transport that
implements the same surface as BrewerTransport and plays a plausible event
stream back, so every sensor, button and service does something visible. It
exists to answer "what does this look like in Home Assistant" before a real
brewer is on the bench.

It is deliberately in its own module and only reachable through an explicit
demo toggle in the config flow, so nothing on the real Bluetooth path can fall
into it by accident.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

_LOGGER = logging.getLogger(__name__)

# How long each simulated step "takes". Short enough to watch, long enough that
# the status sensor visibly moves through its states rather than blinking.
_STEP_SECONDS = 3.0


class SimulatedTransport:
    """Same interface as BrewerTransport; talks to nobody."""

    def __init__(self, address: str, on_line) -> None:
        self._address = address
        self._on_line = on_line
        self._connected = False
        self._hass = None
        self._task: asyncio.Task | None = None

    @property
    def address(self) -> str:
        return self._address

    @property
    def connected(self) -> bool:
        return self._connected

    async def async_connect(self, hass) -> None:
        self._hass = hass
        self._connected = True
        self._emit("is_connected:1")

    async def async_disconnect(self) -> None:
        self._cancel()
        self._connected = False
        self._emit("is_connected:0")

    async def async_send(self, payload: str) -> None:
        """Interpret the framed payload and script a matching event stream."""
        if "<ABORT>" in payload or "<CANCEL>" in payload:
            self._cancel()
            self._emit("notify:Aborted")
            return
        if "<DIALOG>" in payload:
            # A dialog answer resumes the (already running) brew; nothing to do
            # here, the running script continues on its own.
            return
        if "<PG>" in payload and "<PS>" in payload:
            self._start(self._purge_script())
            return

        steps = _count_steps(payload)
        self._start(self._brew_script(steps))

    # -- scripting --------------------------------------------------------

    def _brew_script(self, steps: int):
        async def run():
            try:
                # A dialog roughly a third of the way in, so the "answer a
                # dialog" path is reachable in the demo without a special case.
                dialog_at = max(1, steps // 3)
                for i in range(steps):
                    await asyncio.sleep(_STEP_SECONDS)
                    if i == dialog_at:
                        self._emit("dialog:Add%20grounds%20and%20press%20start")
                        # Wait for the user to answer via the service/button;
                        # for the demo, auto-continue after a short grace so it
                        # never wedges if they do not.
                        await asyncio.sleep(_STEP_SECONDS * 2)
                    self._emit("stepCompleted")
                self._emit("recipeCompleted")
            except asyncio.CancelledError:
                pass
        return run

    def _purge_script(self):
        async def run():
            try:
                await asyncio.sleep(_STEP_SECONDS)
                self._emit("stepCompleted")
                self._emit("recipeCompleted")
            except asyncio.CancelledError:
                pass
        return run

    def _start(self, coro_factory) -> None:
        self._cancel()
        if self._hass is not None:
            self._task = self._hass.async_create_task(coro_factory())

    def _cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    def _emit(self, line: str) -> None:
        result = self._on_line(line)
        if asyncio.iscoroutine(result):
            assert self._hass is not None
            self._hass.async_create_task(result)


def _count_steps(payload: str) -> int:
    """How many steps a framed brew payload contains, for the demo timeline."""
    m = re.search(r"\[.*\]", payload, re.DOTALL)
    if m:
        try:
            return max(1, len(json.loads(m.group(0))))
        except (ValueError, TypeError):
            pass
    return max(1, payload.count('"type"'))

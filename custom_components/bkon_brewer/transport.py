"""Nordic UART transport to the brewer over Home Assistant's Bluetooth stack.

This is the thin I/O layer. It cannot be unit-tested without a brewer, so it is
kept deliberately small and every protocol decision it embodies is documented
and, where it is a guess, labelled as one.

It talks through whatever connectable Bluetooth adapter Home Assistant has --
here that means an ESPHome proxy, since the host container has no radio. That is
transparent to this code: `bleak-retry-connector` routes through the best proxy
in range, so nothing below cares that the brewer is reached over the network.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)

# Nordic UART Service. See docs/PROTOCOL.md.
NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   # write: host -> brewer
NUS_TX_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # notify: brewer -> host

# UNVERIFIED. A classic Nordic UART write is capped at (MTU - 3) bytes, and the
# 20-byte floor is what you get before any MTU negotiation. The app enforces a
# 599-byte recipe ceiling, which only makes sense if longer payloads are split
# across writes -- but exactly how the brewer reassembles them is one of the
# open questions in docs/PROTOCOL.md. 20 is the safe default until a capture
# from real hardware says otherwise; it is a constant here so that is a
# one-line change, not a hunt.
WRITE_CHUNK_SIZE = 20

# Small gap between chunks. Without it, back-to-back writes can outrun a slow
# peripheral's buffer. Also unverified, also deliberately conservative.
INTER_CHUNK_DELAY = 0.03


class BrewerTransport:
    """Owns one BLE link to the brewer.

    Construction does not connect; `async_connect` does. This mirrors how Home
    Assistant expects a device wrapper to behave -- cheap to build, explicit to
    open -- and lets the coordinator own the lifecycle.
    """

    def __init__(self, address: str,
                 on_line: Callable[[str], Awaitable[None] | None]) -> None:
        self._address = address
        self._on_line = on_line
        self._client = None
        self._rx_buffer = bytearray()
        self._lock = asyncio.Lock()

    @property
    def address(self) -> str:
        return self._address

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def async_connect(self, hass) -> None:
        """Establish the link and subscribe to notifications.

        Imports live here rather than at module load so the pure protocol layer
        and its tests never require bleak or Home Assistant to be installed.
        """
        from bleak_retry_connector import establish_connection, BleakClientWithServiceCache
        from homeassistant.components import bluetooth

        ble_device = bluetooth.async_ble_device_from_address(
            hass, self._address, connectable=True)
        if ble_device is None:
            raise BrewerUnavailable(
                f"{self._address} is not reachable by any connectable "
                f"Bluetooth adapter. Move the brewer nearer a proxy, or check "
                f"the proxy is online.")

        self._client = await establish_connection(
            BleakClientWithServiceCache, ble_device, self._address)
        await self._client.start_notify(NUS_TX_CHAR, self._handle_notify)
        _LOGGER.debug("connected to brewer %s", self._address)

    async def async_disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            finally:
                self._client = None

    async def async_send(self, payload: str) -> None:
        """Write a framed payload, chunked to the negotiated write size.

        Serialised behind a lock: two overlapping writes would interleave their
        chunks on the wire and the brewer would receive neither message. A brew
        command and an abort racing is exactly the situation where that must not
        happen.
        """
        if not self.connected:
            raise BrewerUnavailable("not connected")
        data = payload.encode("utf-8")
        async with self._lock:
            for i in range(0, len(data), WRITE_CHUNK_SIZE):
                chunk = data[i:i + WRITE_CHUNK_SIZE]
                await self._client.write_gatt_char(NUS_RX_CHAR, chunk,
                                                   response=False)
                if i + WRITE_CHUNK_SIZE < len(data):
                    await asyncio.sleep(INTER_CHUNK_DELAY)

    async def _handle_notify(self, _char, data: bytearray) -> None:
        """Reassemble notification bytes into lines and dispatch them.

        The brewer's events are newline-free `event:payload` strings, but a
        single logical message can arrive across several notifications. We
        accumulate and split on the frame boundaries the app uses (`}` closing a
        `{msg:...}`, or a bare newline) rather than assuming one notify equals
        one event -- assuming that is how you lose the tail of a long dialog.
        """
        self._rx_buffer.extend(data)
        text = self._rx_buffer.decode("utf-8", errors="replace")

        # Split on newlines if present; otherwise treat each complete {..} frame
        # as one message. Anything trailing stays buffered for the next notify.
        lines, remainder = _split_messages(text)
        self._rx_buffer = bytearray(remainder.encode("utf-8"))
        for line in lines:
            result = self._on_line(line)
            if asyncio.iscoroutine(result):
                await result


def _split_messages(text: str) -> tuple[list[str], str]:
    """Return (complete messages, leftover). Pure, so it *is* testable.

    Handles both shapes seen in the app: newline-delimited lines, and
    `{msg:...}` frames with no delimiter between them.
    """
    if "\n" in text:
        parts = text.split("\n")
        return [p for p in parts[:-1] if p], parts[-1]

    # Frame-delimited: peel off balanced {...} groups from the front.
    out: list[str] = []
    depth = 0
    start = 0
    i = 0
    consumed = 0
    while i < len(text):
        c = text[i]
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            if depth > 0:
                depth -= 1
                if depth == 0:
                    out.append(text[start:i + 1])
                    consumed = i + 1
        i += 1
    return out, text[consumed:]


class BrewerUnavailable(Exception):
    """The brewer could not be reached. Distinct from a protocol error."""

"""Talking to Home Assistant from inside the add-on.

The studio used to hand you a YAML service call to paste into Developer Tools,
which meant the add-on could show you a recipe but never act on one. With
`homeassistant_api: true` the Supervisor proxies the Core API for us, using the
token it already injects -- so Save and Brew do the thing instead of describing
it.

Kept deliberately small: read the library, save, delete, brew, rate. Everything
else the integration already owns. Failures come back as a clear message rather
than an exception, because the UI has to say something useful either way.
"""
from __future__ import annotations

import os

BASE = "http://supervisor/core/api"
TOKEN = os.getenv("SUPERVISOR_TOKEN", "")
DOMAIN = "bkon_brewer"


class HaError(RuntimeError):
    """Home Assistant could not be reached, or refused the call."""


def available() -> bool:
    return bool(TOKEN)


async def _request(method: str, path: str, payload: dict | None = None,
                   params: dict | None = None):
    import aiohttp
    if not TOKEN:
        raise HaError("No Supervisor token — the add-on cannot reach Home "
                      "Assistant. Check homeassistant_api is enabled.")
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, f"{BASE}{path}", headers=headers,
                                   json=payload, params=params) as resp:
            body = await resp.json(content_type=None)
            if resp.status >= 400:
                raise HaError(f"Home Assistant returned {resp.status}: "
                              f"{str(body)[:200]}")
            return body


async def call_service(service: str, data: dict, *, want_response: bool = False):
    """Call a bkon_brewer service. `want_response` returns its response data."""
    params = {"return_response": "true"} if want_response else None
    return await _request("POST", f"/services/{DOMAIN}/{service}", data, params)


async def library() -> list[dict]:
    """Every saved recipe, read off the library sensor's attributes.

    The sensor already carries the whole library -- steps, rating, notes,
    journal, brew count -- so this needs no new integration surface.
    """
    states = await _request("GET", "/states")
    for s in states:
        eid = s.get("entity_id", "")
        if eid.startswith("sensor.") and eid.endswith("_recipe_library"):
            return s.get("attributes", {}).get("recipes", []) or []
    return []

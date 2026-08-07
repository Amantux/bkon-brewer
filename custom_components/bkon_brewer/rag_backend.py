"""Pluggable retrieval backend: LightRAG when configured, local otherwise.

The concierge always has a working answer path -- the built-in TF-IDF retriever
over the local index (knowledge.py). This module layers a *better* path on top:
a LightRAG server backed by Ollama, which does graph retrieval and generates a
written answer from a local model instead of quoting a paragraph.

The design rule is that the upgrade can never be a downgrade. LightRAG runs in a
sidecar container; sidecars restart, models load slowly, a Pi under load times
out. So every call through here falls back to the local retriever on any
failure, and the user sees a slightly less fluent answer rather than an error.
Credentials (the LightRAG API key) live in the config entry, never in code.

Only `LightRagBackend.async_answer` touches the network, and it takes the HTTP
session as an argument, so the request-building logic is testable without
aiohttp or a running server.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

# LightRAG retrieval modes. "hybrid" combines the knowledge graph with vector
# search and is the sensible default; "local"/"global" trade recall for focus.
VALID_MODES = ("hybrid", "local", "global", "naive", "mix")
DEFAULT_MODE = "hybrid"

# LLM generation on a Raspberry Pi is slow. This timeout is generous on purpose
# -- better to wait for a real answer than to fall back to a paragraph quote
# while the model was two seconds from finishing. If it genuinely hangs, the
# fallback still fires, just later.
DEFAULT_TIMEOUT = 45.0


class RagError(Exception):
    """A backend failed. Always caught by answer(); triggers the fallback."""


@dataclass(slots=True)
class LightRagBackend:
    """Client for a LightRAG server. See deploy/ for the server itself."""

    base_url: str
    api_key: str | None = None
    mode: str = DEFAULT_MODE
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if self.mode not in VALID_MODES:
            self.mode = DEFAULT_MODE

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            # LightRAG's server accepts the key either way depending on version;
            # sending both is harmless and saves a round of "which header".
            headers["X-API-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def async_answer(self, session, query: str) -> str:
        """Ask LightRAG. Raises RagError on anything that isn't a clean answer.

        The caller catches RagError and falls back, so this stays strict: a 500,
        a timeout, an empty body and a missing field are all failures, not
        things to paper over with a half-answer.
        """
        url = f"{self.base_url}/query"
        payload = {"query": query, "mode": self.mode}
        try:
            timeout = _timeout(self.timeout)
            async with session.post(url, json=payload, headers=self._headers(),
                                    timeout=timeout) as resp:
                if resp.status == 401 or resp.status == 403:
                    raise RagError(
                        f"LightRAG rejected the API key (HTTP {resp.status}). "
                        f"Check the key in the integration options matches the "
                        f"server's.")
                if resp.status >= 400:
                    raise RagError(f"LightRAG returned HTTP {resp.status}")
                data = await resp.json()
        except RagError:
            raise
        except Exception as ex:                      # noqa: BLE001
            raise RagError(f"LightRAG unreachable: {ex}") from ex

        answer = _extract_answer(data)
        if not answer:
            raise RagError("LightRAG returned an empty answer")
        return answer

    async def async_health(self, session) -> bool:
        """Is the server up? Used to show a clear status, never to gate answers."""
        try:
            async with session.get(f"{self.base_url}/health",
                                   headers=self._headers(),
                                   timeout=_timeout(8.0)) as resp:
                return resp.status < 400
        except Exception:                            # noqa: BLE001
            return False


def _extract_answer(data) -> str:
    """Pull the answer text out, tolerant of LightRAG's response shape.

    Versions have returned the answer under `response`, `data`, or a bare
    string. Checking each rather than assuming one keeps the integration working
    across a server upgrade -- the kind of break that is otherwise silent.
    """
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in ("response", "answer", "data", "result", "text"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _timeout(seconds: float):
    """aiohttp timeout, imported lazily so pure tests need no aiohttp."""
    try:
        from aiohttp import ClientTimeout
    except ImportError:                              # pragma: no cover
        return seconds
    return ClientTimeout(total=seconds)


async def answer_with_fallback(session, backend, local_kb, query: str) -> tuple[str, str]:
    """The single entry point the rest of the integration uses.

    Returns (answer_text, source) where source is "lightrag" or "local", so the
    caller and the logs can see which path served the answer. LightRAG is tried
    first when configured; any failure drops to the local retriever, which is
    why questions keep working even with the sidecar down.
    """
    if backend is not None and session is not None:
        try:
            text = await backend.async_answer(session, query)
            return text, "lightrag"
        except RagError as ex:
            _LOGGER.debug("LightRAG unavailable, using local retriever: %s", ex)
    if local_kb is not None and getattr(local_kb, "ready", False):
        return local_kb.answer(query), "local"
    return ("I don't have the BKON documents available right now. Recipe tweaks "
            "still work.", "none")

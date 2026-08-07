"""Anthropic (Claude) adapter. SDK lazy-imported; floor anthropic>=0.42.0.

`system` is a top-level parameter for Anthropic, not a message role -- one of the
per-vendor specifics the spec calls out. Handled here so callers stay uniform.
"""
from __future__ import annotations

from .base import AIProvider, ProviderError


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str,
                 base_url: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._client = None

    def available(self) -> bool:
        return bool(self._api_key and self._model)

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic     # lazy
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncAnthropic(**kwargs)
        return self._client

    async def complete(self, prompt: str, system: str | None = None,
                       max_tokens: int = 2048) -> str:
        try:
            resp = await self._get_client().messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system or "",                 # top-level, not a message
                messages=[{"role": "user", "content": prompt}],
            )
            # content is a list of blocks; concatenate the text ones.
            return "".join(b.text for b in resp.content
                           if getattr(b, "type", None) == "text")
        except Exception as ex:                      # noqa: BLE001
            raise ProviderError(f"anthropic call failed: {ex}") from ex

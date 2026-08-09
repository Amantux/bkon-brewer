"""Anthropic (Claude) adapter. SDK lazy-imported; floor anthropic>=0.42.0.

`system` is a top-level parameter for Anthropic, not a message role -- one of the
per-vendor specifics the spec calls out. Handled here so callers stay uniform.
"""
from __future__ import annotations

from .base import AIProvider, ProviderError, VisionUnsupported


def _media_type(data: bytes) -> str:
    """From the bytes, not from a filename we may not have."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"




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
                       max_tokens: int = 2048,
                       images: list[bytes] | None = None) -> str:
        content: list | str = prompt
        if images:
            import base64
            content = [{"type": "image", "source": {
                            "type": "base64", "media_type": _media_type(b),
                            "data": base64.b64encode(b).decode()}}
                       for b in images]
            content.append({"type": "text", "text": prompt})
        try:
            resp = await self._get_client().messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system or "",                 # top-level, not a message
                messages=[{"role": "user", "content": content}],
            )
        except Exception as ex:                      # noqa: BLE001
            raise ProviderError(f"anthropic call failed: {ex}") from ex

        # content is a list of blocks; concatenate the text ones. A thinking
        # block carries no `.text`, so a turn that was all deliberation lands
        # here as "" -- which must be reported, not rendered. See ollama.py.
        text = "".join(b.text for b in resp.content
                       if getattr(b, "type", None) == "text").strip()
        if not text:
            raise ProviderError(
                f"{self._model} returned no text (stop reason: "
                f"{getattr(resp, 'stop_reason', None) or 'unknown'}).")
        return text

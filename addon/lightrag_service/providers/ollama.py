"""Ollama adapter — local server or Ollama Cloud, same code, different host.

Cloud is just a host + a bearer key; local needs neither. The SDK is imported
lazily so a deployment that never touches Ollama does not require the package.
"""
from __future__ import annotations

from .base import AIProvider, ChatResult, ProviderError


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, host: str, model: str, api_key: str | None = None) -> None:
        self._host = (host or "").rstrip("/")
        self._model = model
        self._api_key = api_key
        self._client = None

    def available(self) -> bool:
        return bool(self._host and self._model)

    def _get_client(self):
        if self._client is None:
            from ollama import AsyncClient          # lazy: only if used
            headers = ({"Authorization": f"Bearer {self._api_key}"}
                       if self._api_key else None)
            self._client = AsyncClient(host=self._host, headers=headers)
        return self._client

    async def complete(self, prompt: str, system: str | None = None,
                       max_tokens: int = 2048) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = await self._get_client().chat(
                model=self._model, messages=messages,
                options={"num_predict": max_tokens})
            return resp["message"]["content"]
        except Exception as ex:                      # noqa: BLE001
            raise ProviderError(f"ollama call failed: {ex}") from ex

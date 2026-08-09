"""OpenAI-compatible adapter — covers OpenAI, and any endpoint that speaks the
same API (LM Studio, vLLM, llama.cpp server, Together, Groq, ...).

SDK lazy-imported; floor openai>=1.55.3 (older passes a removed `proxies` kwarg
to httpx 0.28 and crashes). The base URL is the knob that points it anywhere.
"""
from __future__ import annotations

from .base import AIProvider, ProviderError


class OpenAICompatProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str,
                 base_url: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._client = None

    def available(self) -> bool:
        # An OpenAI-compatible server may need no key; a model is always required.
        return bool(self._model)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI           # lazy
            kwargs = {"api_key": self._api_key or "not-needed"}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def complete(self, prompt: str, system: str | None = None,
                       max_tokens: int = 2048) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = await self._get_client().chat.completions.create(
                model=self._model, messages=messages, max_tokens=max_tokens)
        except Exception as ex:                      # noqa: BLE001
            raise ProviderError(f"openai call failed: {ex}") from ex

        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        if text:
            return text
        # Reasoning models served over this API put deliberation in a separate
        # field and may finish with no content at all. See ollama.py.
        text = (getattr(choice.message, "reasoning_content", None) or "").strip()
        if text:
            return text
        raise ProviderError(
            f"{self._model} returned no text (finish reason: "
            f"{choice.finish_reason or 'unknown'}).")

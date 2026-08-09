"""Ollama adapter — local server or Ollama Cloud, same code, different host.

Cloud is just a host + a bearer key; local needs neither. The SDK is imported
lazily so a deployment that never touches Ollama does not require the package.
"""
from __future__ import annotations

import json

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

        # Reasoning models (gpt-oss, deepseek-r1, qwen3) split their output:
        # deliberation into `thinking`, the conclusion into `content`. Asked for
        # a JSON tool call, gpt-oss reasons "we need to call the tool" and often
        # stops there -- `content` empty, nothing usable anywhere. Turning
        # thinking off puts the whole answer back in `content`, which is where
        # every other provider puts it. Not every model accepts the parameter,
        # so a rejection means retry without it rather than fail.
        try:
            resp = await self._call(messages, max_tokens, think=False)
        except _ThinkUnsupported:
            resp = await self._call(messages, max_tokens, think=None)

        msg = resp["message"]
        content = (msg.get("content") or "").strip()
        if content:
            return content

        # Still nothing in content: if the model wrote the JSON we asked for
        # into its deliberation, take it from there. Only the JSON -- returning
        # raw chain-of-thought as a reply shows the user "We need to call the
        # tool." in place of an answer, which is worse than an error.
        salvaged = _json_in((msg.get("thinking") or ""))
        if salvaged:
            return salvaged

        raise ProviderError(
            f"{self._model} returned no answer (finished: "
            f"{resp.get('done_reason') or 'unknown'}). Reasoning models can "
            f"spend their whole budget thinking; try a larger token budget or "
            f"a model that answers directly.")

    async def _call(self, messages, max_tokens, think):
        kwargs = {"model": self._model, "messages": messages,
                  "options": {"num_predict": max_tokens}}
        if think is not None:
            kwargs["think"] = think
        try:
            return await self._get_client().chat(**kwargs)
        except Exception as ex:                      # noqa: BLE001
            text = str(ex).lower()
            if think is not None and ("think" in text or "does not support" in text):
                raise _ThinkUnsupported from ex
            raise ProviderError(f"ollama call failed: {ex}") from ex


class _ThinkUnsupported(Exception):
    """This model rejects the `think` parameter; ask again without it."""


def _json_in(text: str) -> str:
    """The first balanced JSON object in `text`, or "" if there is none."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        json.loads(candidate)
                    except ValueError:
                        break
                    return candidate
        start = text.find("{", start + 1)
    return ""

"""Provider-agnostic LLM interface, per Amantux/edibl docs/chat-and-providers.md.

The service never imports a vendor SDK directly; each adapter does, lazily.
Selecting Ollama vs Anthropic vs an OpenAI-compatible endpoint is a config
change, not a code change -- the whole point of the pattern.

BKON's use is single-turn completion (LightRAG does its own retrieval and hands
this layer one prompt), so the interface here is the completion subset of the
full spec: available() + complete(). The shapes match the spec so an adapter can
grow chat/tool support later without changing callers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(RuntimeError):
    """A provider is misconfigured or a call failed. Callers surface it as 502."""


@dataclass(slots=True)
class ChatResult:
    """Normalized return. Text only here; tool_calls kept for interface parity
    with the spec's ChatResult so this can grow into the full agent loop."""

    content: str = ""


class AIProvider(ABC):
    """One vendor. name is stable and used for per-provider config namespacing."""

    name: str = "base"

    @property
    def model(self) -> str:
        """The model in use, for the status page.

        Adapters keep it in `_model`; without this the status page read a
        `model` attribute that never existed and reported None, so a user whose
        UI-saved model was shadowing their configured one had no way to see it.
        """
        return getattr(self, "_model", "") or ""

    @abstractmethod
    def available(self) -> bool:
        """Has everything it needs (key/host/model) to make a call?"""

    @abstractmethod
    async def complete(self, prompt: str, system: str | None = None,
                       max_tokens: int = 2048) -> str:
        """One completion. Raises ProviderError on failure."""

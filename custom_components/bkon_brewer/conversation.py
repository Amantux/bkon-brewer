"""A conversation agent, so the concierge is reachable through Assist.

Thin adapter only: the routing and the answers live in `concierge`, `advisor`
and `knowledge`, all pure and tested. This file does nothing but hand Assist's
text to the concierge and hand its reply back, so a change in Home Assistant's
conversation API can never touch the logic that decides what to say.
"""
from __future__ import annotations

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import concierge, rag_backend
from .const import DOMAIN
from .knowledge import KnowledgeBase
from .library import RecipeLibrary


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([BkonConciergeAgent(hass, entry)])


class BkonConciergeAgent(conversation.ConversationEntity):
    """Answers BKON questions and previews recipe tweaks from natural language."""

    _attr_has_entity_name = True
    _attr_name = "BKON Concierge"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_concierge"

    @property
    def supported_languages(self) -> list[str]:
        return ["en"]

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        store = self.hass.data.get(DOMAIN, {})
        library: RecipeLibrary | None = store.get("library")
        kb: KnowledgeBase | None = store.get("kb")
        recipes = ({r["name"]: library.get(r["id"]) for r in library.list()}
                   if library else {})

        reply = concierge.respond(user_input.text, recipes, kb)
        if reply.kind == "answer":
            # Same LightRAG-then-local path the ask service uses, so Assist and
            # the service never diverge on how a question is answered.
            session = async_get_clientsession(self.hass)
            text, _src = await rag_backend.answer_with_fallback(
                session, store.get("rag"), kb, user_input.text)
            reply.text = text

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(reply.text)
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id)

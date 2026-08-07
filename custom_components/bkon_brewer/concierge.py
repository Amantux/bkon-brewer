"""Routing between recipe customisation and document questions.

The concierge decides what a plain-language message wants: to change a recipe,
or to ask a question. That decision is the whole of its intelligence and it is
kept here, pure, so it can be tested without Home Assistant, a conversation
pipeline, or a real brewer.

The distinction it has to get right is the subtle one:

    "make my morning cup stronger"   -> customise the saved recipe
    "how do I make coffee stronger"  -> answer from the documents

Both contain "stronger". What separates them is whether a *saved recipe* is
being referred to. So: an adjustment intent plus a recipe reference is a
customisation; an adjustment intent with a question shape, or none, is a
question. When it is ambiguous, it asks rather than guesses -- changing the
wrong recipe is worse than a clarifying question.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# An error code (C:x M:y) or an obvious fault phrase routes to diagnosis rather
# than plain retrieval -- the person wants a fix, not a paragraph.
_ERROR_RE = re.compile(r"C\s*:?\s*\d+\s*M\s*:?\s*\d+", re.IGNORECASE)
_FAULT_WORDS = ("not sealed", "won't start", "wont start", "error", "fault",
                "stuck", "leak", "no water", "won't brew", "wont brew")

from . import advisor, diagnostics
from .protocol import recipe as R

_QUESTION_WORDS = ("how", "what", "why", "when", "where", "which", "who",
                   "can i", "do i", "should i", "is it", "does")


@dataclass(slots=True)
class Reply:
    text: str
    kind: str = "answer"                       # answer | customise | clarify
    recipe_name: str | None = None
    new_steps: list[R.Step] | None = field(default=None)
    #: True when the text is a finished answer (a diagnosis, a clarify) that must
    #: NOT be re-run through the RAG backend. Only a plain document question
    #: (composed=False) goes to LightRAG/local retrieval in the service layer.
    composed: bool = False


def respond(message: str, recipes: dict[str, list[R.Step]], kb) -> Reply:
    """Route one message. `recipes` is name -> steps; `kb` is a KnowledgeBase.

    Neither is mutated. A customisation returns the proposed steps for the caller
    to preview or save; it does not save them itself, because "make it stronger"
    is a request to see a change, not a command to overwrite a saved recipe.
    """
    text = message.strip()
    if not text:
        return Reply("Ask me a question about your BKON, or tell me how to "
                     "tweak a saved recipe.", kind="clarify")

    intents = advisor.parse_feedback(text)
    named = _match_recipe(text, recipes)
    looks_like_question = _is_question(text)

    # An adjustment aimed at a recipe -> customise.
    if intents and (named or _refers_to_a_recipe(text)) and not looks_like_question:
        if named is None:
            if len(recipes) == 1:
                named = next(iter(recipes))     # only one, no ambiguity
            else:
                names = ", ".join(sorted(recipes)) or "none saved yet"
                return Reply(
                    f"Which recipe should I adjust? You have: {names}.",
                    kind="clarify")
        result = advisor.customize(recipes[named], text)
        if result.not_understood:
            return _as_question(text, kb)       # fall back to answering
        head = (f"Here's **{named}** made "
                f"{_describe_intents(intents)}:\n")
        return Reply(head + result.summary(), kind="customise",
                     recipe_name=named, new_steps=result.steps)

    # A fault or an error code wants diagnosis (cause + fix), not retrieval.
    low = text.lower()
    if _ERROR_RE.search(text) or any(w in low for w in _FAULT_WORDS):
        d = diagnostics.diagnose(text, kb=kb)
        body = f"**{d.summary}**\n{d.cause}\n\nFix: {d.fix}"
        if d.source:
            body += f"\n  — {d.source}"
        return Reply(body, kind="answer", composed=True)

    # Otherwise it is a question for the documents.
    return _as_question(text, kb)


def _as_question(text: str, kb) -> Reply:
    if kb is None or not getattr(kb, "ready", False):
        return Reply(
            "I don't have the BKON documents indexed yet, so I can only help "
            "with recipe tweaks for now. Build the knowledge base to enable "
            "questions (see the README).", kind="answer")
    return Reply(kb.answer(text), kind="answer")


def _is_question(text: str) -> bool:
    low = text.lower().strip()
    return low.endswith("?") or low.startswith(_QUESTION_WORDS)


def _refers_to_a_recipe(text: str) -> bool:
    """Does the message point at a recipe without naming one? ("make it hotter")."""
    return bool(re.search(r"\b(it|this|that|my|the recipe|the brew)\b",
                          text.lower()))


def _match_recipe(text: str, recipes: dict) -> str | None:
    """Find a saved recipe named in the message, longest name first.

    Longest-first so "morning pour over" wins over a recipe merely called
    "morning" when both exist -- a shorter name is easy to match by accident
    inside a longer one.
    """
    low = text.lower()
    for name in sorted(recipes, key=len, reverse=True):
        if name.lower() in low:
            return name
    return None


def _describe_intents(intents: list[str]) -> str:
    words = {
        "stronger": "stronger", "weaker": "lighter", "hotter": "hotter",
        "cooler": "cooler", "less_bitter": "less bitter",
        "more_bitter": "more bitter", "faster": "faster", "slower": "slower",
        "bigger": "bigger", "smaller": "smaller",
    }
    parts = [words.get(i, i) for i in intents]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]

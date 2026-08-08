"""Agent chat loop for the recipe studio. Provider-agnostic, testable.

Follows the edibl chat-and-providers pattern (§4): a small tool loop where the
model either calls a tool or gives a final answer, and tool results are fed back
as plain text. The portable trick from that spec (§2) is used instead of any
vendor's tool-calling API — the model is asked to reply with JSON, and the JSON
is parsed. That keeps this identical across Ollama, Anthropic and an
OpenAI-compatible endpoint, since all it needs from a provider is `complete()`.

Pure over its inputs: the provider and the tool registry are injected, so the
whole loop is tested with a fake provider that returns a tool call then an
answer -- no model, no network, no Home Assistant.
"""
from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field

MAX_ITERS = 4          # tool rounds before we force a plain answer


@dataclass(slots=True)
class Action:
    """A tool the model invoked, for the UI to render as a "what happened" chip."""

    tool: str
    args: dict
    result: dict


@dataclass(slots=True)
class ChatTurn:
    reply: str
    steps: list[dict] | None = None        # the recipe, if a tool changed it
    actions: list[Action] = field(default_factory=list)


#: One line per tool, rendered into the system prompt. Only the tools actually
#: in the registry are described -- `answer_docs` disappears when the LightRAG
#: half of the add-on is switched off, and the model is never told about a tool
#: it cannot call.
TOOL_DOCS = {
    "build_recipe": 'args {"description": str}   build a new recipe from a description',
    "adjust_recipe": 'args {"feedback": str}      tune the CURRENT recipe (stronger, less bitter, hotter, bigger, faster...)',
    "lint_recipe": "args {}                     check the CURRENT recipe for problems",
    "diagnose": 'args {"text": str}          explain an error code or symptom',
    "answer_docs": 'args {"query": str}         answer a how-to question from the machine\'s manuals',
}

_SYSTEM_HEAD = """You are the assistant in a BKON coffee-brewer recipe studio. You help
the user build and tune a recipe, and answer questions about the machine.

You have tools. To use one, reply with ONLY a JSON object:
  {"tool": "<name>", "args": { ... }}
When you are ready to reply to the user, respond with ONLY:
  {"answer": "<your message to the user>"}

Tools:
"""

_SYSTEM_TAIL = """
Rules:
- Reply with a single JSON object and nothing else.
- After a tool runs you get its result; use it, then either call another tool or answer.
- Keep answers short and practical. Refer to the recipe you changed by what changed.
- Tuning the recipe is a tool call, not advice: if the user says it should be
  stronger, less bitter, hotter or bigger, call adjust_recipe with their words
  as the feedback rather than describing what they could change."""


def build_system(tools) -> str:
    """The system prompt for exactly the tools available this turn."""
    lines = []
    for name in tools:
        doc = TOOL_DOCS.get(name, "args {}")
        lines.append(f"- {name:<14} {doc}")
    return _SYSTEM_HEAD + "\n".join(lines) + "\n" + _SYSTEM_TAIL


def _extract_json(text: str) -> dict | None:
    """Pull a JSON object out of a model reply, tolerant of fences and prose.

    Models wrap JSON in ```json fences or add a sentence around it; this finds
    the first balanced object. Returns None if there is no usable object, so the
    caller can treat a plain-text reply as a final answer rather than crashing.
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if not candidate:
        return None
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None


def _recipe_context(steps: list[dict] | None) -> str:
    if not steps:
        return "The recipe is currently empty."
    lines = ["The current recipe has these steps:"]
    for i, s in enumerate(steps, 1):
        vals = ", ".join(f"{k}={v}" for k, v in s.get("values", {}).items())
        lines.append(f"  {i}. {s.get('type')} ({vals})")
    return "\n".join(lines)


async def run_chat(provider, message: str, steps: list[dict] | None, tools: dict,
                   *, history: list[dict] | None = None,
                   max_iters: int = MAX_ITERS) -> ChatTurn:
    """One conversational turn with tool use.

    `tools` maps a name to a callable ``fn(args, steps) -> (result_dict,
    new_steps_or_None)``. A tool that changes the recipe returns the new steps;
    the loop carries them forward so a later tool sees the change, and the final
    turn reports them to the UI.
    """
    steps = list(steps or [])
    system = build_system(tools)
    actions: list[Action] = []
    transcript = [f"User: {message}", _recipe_context(steps)]
    if history:
        # A short prior context, newest last. Kept small; the studio is
        # single-turn-ish and the current recipe is the real state.
        for h in history[-4:]:
            transcript.insert(0, f"{h.get('role', 'user')}: {h.get('content', '')}")

    for _ in range(max_iters):
        prompt = "\n".join(transcript) + "\nRespond with a single JSON object."
        raw = await provider.complete(prompt, system=system)
        obj = _extract_json(raw)

        # No JSON at all -> treat the whole reply as the answer.
        if obj is None:
            return ChatTurn(reply=raw.strip(), steps=steps or None, actions=actions)

        if "answer" in obj:
            return ChatTurn(reply=str(obj["answer"]).strip(),
                            steps=steps or None, actions=actions)

        name = obj.get("tool")
        fn = tools.get(name)
        if fn is None:
            # Unknown tool: tell the model, let it recover, don't crash the turn.
            transcript.append(
                f"Result of {name}: error, no such tool. Use one of: "
                f"{', '.join(tools)}.")
            continue

        args = obj.get("args") or {}
        try:
            out = fn(args, steps)
            if inspect.isawaitable(out):             # answer_docs hits the RAG
                out = await out
            result, new_steps = out
        except Exception as ex:                      # noqa: BLE001
            result, new_steps = {"error": str(ex)}, None
        if new_steps is not None:
            steps = new_steps
        actions.append(Action(tool=name, args=args, result=result))
        transcript.append(f"Result of {name}: {json.dumps(result)[:600]}")

    # Loop exhausted: one more call, forced to answer.
    transcript.append("Give the user a final answer now as {\"answer\": ...}.")
    raw = await provider.complete("\n".join(transcript), system=system)
    obj = _extract_json(raw) or {}
    reply = obj.get("answer") or raw.strip()
    return ChatTurn(reply=str(reply).strip(), steps=steps or None, actions=actions)

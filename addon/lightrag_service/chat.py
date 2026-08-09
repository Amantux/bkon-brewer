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
    "score_recipe": 'args {}                     score the CURRENT recipe and comment on it',
    "list_recipes": "args {}                     list the user's saved recipes with their ratings and brew counts",
    "open_recipe": 'args {"name": str}         load a saved recipe into the builder',
    "save_recipe": 'args {"name": str}         save the CURRENT recipe (asks the user first)',
    "brew_recipe": 'args {"name": str}         brew a saved recipe (asks the user first)',
    "answer_docs": 'args {"query": str}         answer a how-to question from the machine\'s manuals',
    "show_diagram": 'args {"query": str}         find a diagram, schematic or screenshot to SHOW the user',
    "look_up": 'args {"query": str}         exact lookup: an error code (C:3 M:5), a part number, a diagram label (V5)',
}

#: What the machine actually is, from the confirmed documents (docs/INTEL.md).
#: Without this the assistant is a generic tool-caller that happens to hold
#: brewing tools -- it could adjust a vacuum without knowing what a vacuum does.
_GROUNDING = """What you need to know about this machine:
- It brews under vacuum (RAIN). The vacuum is the point: it sets CONCENTRATION.
  Steep time sets flavour INTENSITY. Temperature is an ordinary brewing variable.
- Move the vacuum in steps of about 2 kPa, and steep in steps of 5-10 s. That is
  the documented dial-in convention, not a guess.
- Base recipes: low-temp tea starts 175 F / 24 kPa, high-temp 205 F / 20 kPa --
  a HOTTER brew starts from a SHALLOWER vacuum. In a multi-vacuum sequence, if
  the first is X kPa the next is about X+2 and the third about X+1. Delicate leaf
  uses ONE vacuum, a short steep, and water front-loaded.
- Accepted ranges: temperature 140-212 F, vacuum 0-60 kPa, purge pressure 25-35
  kPa, fill/rinse 0-600 ml, every time 0-180 s. Outside these it will not brew.
- A recipe must fit 599 bytes to send over Bluetooth.
- Steps run in order: start (heat) -> fill -> vacuum (extract) -> purge
  (separate grounds) -> brew out. A dialog step stops and asks the operator."""

_SYSTEM_HEAD = """You are the assistant in a BKON coffee-brewer recipe studio. You help
the user build and tune a recipe, and answer questions about the machine.

You have tools. To use one, reply with ONLY a JSON object, like:
  {"tool": "lint_recipe", "args": {}}
When you are ready to reply to the user, respond with ONLY:
  {"answer": "I deepened the vacuum to 26 kPa, which will read stronger."}
Those are worked examples, not templates -- write your own words in the
"answer" field. Never send an angle-bracket placeholder back.

Tools:
"""

_SYSTEM_TAIL = """
Rules:
- Reply with a single JSON object and nothing else.
- After a tool runs you get its result; use it, then either call another tool or answer.
- Keep answers short and practical. Refer to the recipe you changed by what changed.
- save_recipe and brew_recipe do not act immediately: they ask the user, who
  confirms or declines. When one returns "awaiting confirmation", say what you
  have queued and stop -- do not call it again and do not pretend it happened.
- For an error code, a part number or a diagram label, call look_up rather than
  searching the documents: those are identifiers, and near-enough is wrong.
- Most of this machine's documentation is pictures. When the answer is a
  location, a wiring path, a part, a menu screen or "which one is it?", call
  show_diagram and let the picture do the work -- then say in one line what to
  look at in it. Do not describe a diagram you have not been shown.
- Tuning the recipe is a tool call, not advice: if the user says it should be
  stronger, less bitter, hotter or bigger, call adjust_recipe with their words
  as the feedback rather than describing what they could change."""

#: The reply is rendered as Markdown, so it should be written as Markdown.
_FORMATTING = """How to write your answer (it is rendered as Markdown):
- Use **bold** for values the user should notice, and `code` for step keys.
- Use a numbered list for a sequence of actions, a bulleted list otherwise.
- Use a TABLE whenever you are comparing things -- recipes against each other,
  several options, before-and-after, or a list with more than one attribute per
  row. Sort the rows in whatever order actually helps: strongest first, most
  recent first, worst problem first. Say what you sorted by.
- Keep it short. Two or three sentences plus a list or table beats a paragraph."""


def build_system(tools) -> str:
    """The system prompt for exactly the tools available this turn."""
    lines = []
    for name in tools:
        doc = TOOL_DOCS.get(name, "args {}")
        lines.append(f"- {name:<14} {doc}")
    return (_SYSTEM_HEAD + "\n".join(lines) + "\n" + _SYSTEM_TAIL
            + "\n\n" + _GROUNDING + "\n\n" + _FORMATTING)


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


def _is_placeholder(text: str) -> bool:
    """Did the model send the example back instead of writing something?

    Small models sometimes echo the shape they were shown --
    `{"answer": "<your message to the user>"}` -- and an angle-bracketed stub
    rendered as a reply is worse than an error, because it looks like the app
    generated it. Cheap to detect and always wrong, so always retried.
    """
    t = text.strip()
    return bool(t.startswith("<") and t.endswith(">") and "\n" not in t)


async def run_chat(provider, message: str, steps: list[dict] | None, tools: dict,
                   *, history: list[dict] | None = None, context: str = "",
                   on_step=None, max_iters: int = MAX_ITERS) -> ChatTurn:
    """One conversational turn with tool use.

    `on_step(kind, name)` is called as the turn progresses -- "thinking" before
    each model call, "tool" as each tool starts -- so a caller can show what is
    happening instead of a silent wait. It must never raise; a progress reporter
    that breaks a turn would be worse than no progress at all.

    `tools` maps a name to a callable ``fn(args, steps) -> (result_dict,
    new_steps_or_None)``. A tool that changes the recipe returns the new steps;
    the loop carries them forward so a later tool sees the change, and the final
    turn reports them to the UI.
    """
    steps = list(steps or [])
    system = build_system(tools)
    actions: list[Action] = []
    # `context` is what the user is looking at -- which page, and anything that
    # page knows (a recipe's tasting history, an error on screen). Given to the
    # model so a suggestion can be about the thing in front of them rather than
    # generic advice.
    transcript = [f"User: {message}", _recipe_context(steps)]
    if context:
        transcript.insert(1, f"Where the user is: {context}")
    if history:
        # A short prior context, newest last. Kept small; the studio is
        # single-turn-ish and the current recipe is the real state.
        for h in history[-4:]:
            transcript.insert(0, f"{h.get('role', 'user')}: {h.get('content', '')}")

    def report(kind, name=""):
        if on_step is None:
            return
        try:
            on_step(kind, name)
        except Exception:                            # noqa: BLE001
            pass                                     # never break a turn for this

    for _ in range(max_iters):
        report("thinking")
        prompt = "\n".join(transcript) + "\nRespond with a single JSON object."
        raw = await provider.complete(prompt, system=system)
        obj = _extract_json(raw)

        # No JSON at all -> treat the whole reply as the answer, unless there
        # was no reply. A blank is not an answer: rendering "" shows an empty
        # bubble, which reads as a broken app rather than as a model that said
        # nothing. Nudge once, then say so plainly.
        if obj is None:
            if raw.strip():
                return ChatTurn(reply=raw.strip(), steps=steps or None,
                                actions=actions)
            transcript.append(
                "You replied with nothing. Reply now with a single JSON "
                "object: {\"answer\": \"...\"}.")
            continue

        if "answer" in obj:
            answer = str(obj["answer"]).strip()
            if answer and not _is_placeholder(answer):
                return ChatTurn(reply=answer, steps=steps or None,
                                actions=actions)
            transcript.append(
                "That was not an answer -- you sent back the example. Write "
                "your own words to the user this time.")
            continue

        name = obj.get("tool")
        fn = tools.get(name)
        if fn is None:
            # Unknown tool: tell the model, let it recover, don't crash the turn.
            transcript.append(
                f"Result of {name}: error, no such tool. Use one of: "
                f"{', '.join(tools)}.")
            continue

        args = obj.get("args") or {}
        report("tool", name)
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
    reply = str(obj.get("answer") or raw or "").strip()
    if not reply:
        # Out of rounds with nothing to show. Say which tools did run, so the
        # turn is still worth something and the failure is legible.
        ran = ", ".join(dict.fromkeys(a.tool for a in actions))
        reply = ("I couldn't put an answer together for that. "
                 + (f"I did run: {ran}. " if ran else "")
                 + "Try asking it a different way.")
    return ChatTurn(reply=reply, steps=steps or None, actions=actions)

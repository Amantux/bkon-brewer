# How this interface is designed

Notes on the visual approach, written down so it survives the next change. Not
a style guide anyone has to obey — a record of the decisions that produced the
look, and the reasoning that would let you make the next one consistently.

The subject is a commercial vacuum brewer that costs more than a car payment
and lives on a counter in a coffee shop. The interface should feel like
equipment, not like an app: precise, quiet, and confident about numbers. That
single sentence produced most of what follows.

---

## The ground rules

**Instrument, not dashboard.** Everything on screen is either a value you can
change or a consequence of one. There is no chrome for its own sake — no cards
wrapping single numbers, no icons where a word is clearer, no progress bars
that do not measure anything. The byte gauge exists because 599 is a real
ceiling you can hit; nothing else on the page decorates.

**The numbers are the content.** Temperatures, pressures, volumes and times are
what this machine is. They get a monospace face, tabular figures, and enough
weight to read at a glance. Prose supports the numbers, never the reverse.

**Say what a value means, not just what it is.** "24 kPa" is meaningless
without a feel for the range, so Easy mode pairs every slider with a plain
reading: *standard — where the base recipes sit*, *outside the 25–35 the app
accepts*. The readings come from the documented base recipes, so a value the
machine will reject says so rather than being given a flattering description.

**Show the working, then fold it away.** A tool-using answer streams its steps
live — *reading the manuals*, *tuning the recipe* — then collapses to a `3 steps`
disclosure once the answer arrives. Sources do the same. You can always get to
how something was arrived at; you are never made to read it first.

---

## Colour

The palette is a warm near-neutral ground with **one accent** and a small set of
**semantic step colours**. Semantic colour is not decoration and is never spent
on anything else.

| Token | Job |
|---|---|
| `--accent` | The one interactive colour: focus, selection, primary action |
| `--t-start` | Heat — also carries error, because both mean "attention" |
| `--t-vacuum` | The vacuum, the machine's defining mechanism |
| `--warn` | Something needs a decision before it proceeds |
| `--ink`, `--ink-soft`, `--ink-faint` | Three levels of text, no more |
| `--line`, `--line-2` | Structure that recedes |

Each step type owns a colour, set once per card as `--dot` and inherited by
everything in it. A vacuum step reads as a vacuum step from across the room
without anyone labelling it twice.

The neutrals are biased slightly warm rather than being pure greys. A pure
mid-grey reads as unconsidered; a grey with a hint of the accent in it reads as
chosen.

Both themes are designed, not inverted. The palette is defined as tokens on
`:root`, redefined under `@media (prefers-color-scheme: dark)`, and redefined
again under `:root[data-theme="…"]` so an explicit toggle beats the OS
preference in both directions. **Components never reference a colour inside a
media query** — only through a token. That single rule is what keeps the second
theme from rotting.

---

## Type

Three faces, three jobs, no overlap:

- **Sans** for everything you read as language.
- **Mono** for anything you would compare against another value — a
  temperature, a byte count, a part number, an error code. Always with
  `font-variant-numeric: tabular-nums` so digits line up in a column.
- **Uppercase mono with wide tracking** for labels that name a region rather
  than say something: `SOURCES`, `SERVES`. Small, faint, and never a sentence.

The scale is seven fixed steps, `--fs-xs` through `--fs-3xl`. Every size on the
page is one of them. When something needs to be "slightly bigger", it moves a
step or the layout is wrong — a one-off `15px` is how a type scale dies.

---

## Shape and space

Four radius tokens, each with a meaning: `--r-chip` for something round-ish and
small, `--r-control` for anything you click or type into, `--r-card` for a
container, `--r-pill` for an inline action. Nothing invents a fifth.

Layout is flex and grid with `gap`. Sibling spacing is never per-element
margins, which collapse and double in ways nobody can predict from reading the
CSS. Wide content — tables, diagrams, code — gets `overflow-x: auto` on its own
container so the page body never scrolls sideways.

Related controls sit together and get one label between them, rather than each
carrying its own. A step card is a single object: grip, index, type, values,
and its plain sentence, in that reading order.

---

## Motion

Motion earns its place by explaining something. The running step in a trace
pulses because it is running. A card lifts while dragged because it is being
carried. A disclosure triangle rotates because it has opened.

There is no page-load choreography, no scroll-triggered reveal, nothing that
moves to show that it can. Everything animated respects
`prefers-reduced-motion`, and every animation is short enough that a fast user
never waits for it.

Drag uses Pointer Events — one code path for mouse, pen and touch — with
`touch-action: none` on the grip. The gap that opens for a dropped card is
absolutely positioned, because a flow element re-lays-out the list underneath
the transforms and produces a visible jump.

---

## Words

Copy is written from the user's side of the screen.

- Controls say what will happen: **Open original**, **Make three sizes**, **Brew
  it**. Then the confirmation uses the same verb.
- Errors say what went wrong and what to do: *"gemma4:31b returned no answer
  three times. This model may not answer reliably here — a non-reasoning model
  is a better fit for the studio."* No apology, no blame, a next step.
- Nothing is described as easy, simple or just. If it were, it would not need
  the sentence.
- Uncertainty is stated. When two documents disagree about a service phone
  number, the answer says they disagree instead of picking one confidently.

---

## Structure carries meaning

Numbering, dividers and eyebrows encode something true or they are not used.
Steps are numbered because they run in order. A figure says *4 of 16* because it
is genuinely the fourth page of a procedure. A run of pages that share no
subject gets "pages 12–18" rather than an invented title — the honest label is
the better one.

---

## Density

This is an operator's tool, so it is dense — but density comes from removing
chrome, never from shrinking type or crowding targets. Touch targets stay at
least 44px. When a screen has too much on it the answer is a disclosure, not a
smaller font: sources collapse, tool traces collapse, the wiki nav collapses.
Default to the shortest useful view, and let anyone who wants the rest ask.

---

## What this deliberately is not

- **Not a phone app in a browser.** No bottom tab bar, no hamburger, no modal
  stack. It is a document with instruments on it.
- **Not friendly.** No mascots, no exclamation marks, no emoji as section
  markers. The machine is serious equipment and the interface matches it.
- **Not themed after coffee.** No brown, no burlap, no steam. The subject is a
  vacuum extraction device; the palette comes from instrumentation, not from
  the drink.
- **Not animated for delight.** See Motion.

---

## The test that keeps it honest

[`tests/test_webroot.py`](../tests/test_webroot.py) checks the page
structurally: that every class rendered has a rule, that every handler has an
element and every element a handler, that markup is balanced, that focus states
exist and animations respect reduced motion.

It exists because of a specific failure: Easy mode was toggled, saved and
re-rendered while `render()` never read the flag — the feature was fully
present and entirely disconnected. A test asking whether `flowText()` existed
passed. It now asks whether it is **called**, which is the only version of the
question that catches a feature that is wired to nothing.

That is the general lesson, and it applies to the visuals as much as the logic:
**check the thing is connected, not that it is present.**

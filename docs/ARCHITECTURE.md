# How this project is built

The map you want when returning to this cold. What the pieces are, why they are
arranged this way, and which parts will bite you.

---

## Two halves, deliberately separable

```
custom_components/bkon_brewer/     the Home Assistant integration
    talks Bluetooth to the brewer · owns the recipe library · entities & services
    works completely on its own, with no add-on and no model

addon/                             an optional Home Assistant add-on
    lightrag_service/              FastAPI service: documents, chat agent, studio API
    webroot/index.html             the whole browser UI, one file
```

The integration is the product. The add-on is an upgrade: it makes answers
semantic instead of keyword-based, adds the recipe studio, and reads the
machine's documents. **Nothing about brewing needs it.** If the add-on is
stopped, the integration falls back to its own retriever and keeps working —
that fallback is a design constraint, not a nicety, because a coffee machine
should not stop working when a container does.

### The vendored core, and why

`addon/lightrag_service/bkon_core/` is a **copy** of the integration's pure
logic — the encoder, the advisor, diagnostics, templates, the knowledge index,
the `.bbp` writer. Not an import: the add-on runs in its own container and
cannot import from `custom_components/`.

A copy drifts. So `scripts/check_core_sync.py` compares them byte for byte and
`tests/test_core_sync.py` runs it as part of the suite — **editing one and not
the other fails CI**. When you change anything under `protocol/` or the shared
modules, copy it across:

```bash
cp custom_components/bkon_brewer/protocol/recipe.py \
   addon/lightrag_service/bkon_core/protocol/recipe.py
python3 scripts/check_core_sync.py
```

---

## The layers, top to bottom

| Layer | Where | Rule |
|---|---|---|
| Entities & services | `__init__.py`, `sensor.py`, `services.yaml` | Thin. Schema validation and delegation, nothing clever. |
| Coordination | `coordinator.py` | Owns brew state. The only thing that knows a brew is in progress. |
| Transport | `transport.py` | Nordic UART over BLE. The one place that touches hardware. |
| Protocol | `protocol/` | **Pure.** No I/O, no Home Assistant, no Bluetooth. |
| Library | `library.py` | Recipe CRUD, ratings, journal, brew history. Persists via HA's store. |
| Language | `concierge.py`, `advisor.py`, `nl_recipe.py`, `diagnostics.py` | Pure. Routing and recipe reasoning. |
| Retrieval | `knowledge.py`, `rag_backend.py` | Local keyword index; delegates to the add-on when configured. |

**`protocol/` is pure on purpose.** The encoding rules recovered from the vendor
app are subtle and fail silently — a recipe that encodes "nearly right" still
brews, just not the drink you asked for, and the only symptom is disappointing
coffee. Keeping the layer pure means those rules are tested against known-good
output instead of discovered by drinking the results.

---

## Data flow

**Brewing.** Service call → library lookup (name + optional size) → `R.prepare()`
applies the vendor's serialisation rules → `encode_wire()` produces XML
step-tags → `frame()` wraps in `{msg:1:…}` → transport writes it.
`validate()` measures the *JSON* form against 599 bytes because that is what the
app measures, even though the JSON is not what is sent.

**Asking.** Question → `concierge.py` routes it (tune / document / diagnose) →
either pure local logic or the add-on's `/ask` → answer, plus sources when the
add-on answered.

**The studio.** Browser → add-on `/chat` → `chat.py` tool loop → tools that are
either pure (vendored core) or reach Home Assistant (guarded, see below) →
reply, changed steps, and any actions the browser renders.

---

## The chat agent

`addon/lightrag_service/chat.py` is a provider-agnostic tool loop. The model is
asked to answer with a single JSON object — `{"tool": …}` or `{"answer": …}` —
which is parsed. No vendor tool-calling API, so the same loop works on Ollama,
Anthropic and any OpenAI-compatible endpoint; a provider only has to implement
`complete()`.

Twelve tools: `build_recipe`, `adjust_recipe`, `lint_recipe`, `diagnose`,
`score_recipe`, `answer_docs`, `show_diagram`, `look_up`, `list_recipes`,
`open_recipe`, `save_recipe`, `brew_recipe`. Tools are registered **only when
they can work** — no documents means no `answer_docs`, no described figures
means no `show_diagram`. A tool the model can call that can never return
anything is worse than no tool.

### Anything touching Home Assistant asks first

The add-on holds a supervisor token that could call any service in Home
Assistant. The boundary is an allow-list, not a convention:

- **Reads** (`list_recipes`, `open_recipe`) need a session grant. The first
  attempt returns `awaiting_confirmation`, the browser shows a chip, and the
  grant lasts for that conversation and is **never persisted** — a permission
  that outlives the conversation it was granted in is one nobody remembers
  giving.
- **Writes** (`save_recipe`, `brew_recipe`) never execute in the tool at all.
  They return a request; the user presses the button.
- `/chat/confirm` accepts exactly four actions, all `bkon_brewer`.

`tests/test_ha_permission.py` walks the source with `ast` and fails if any tool
mentions `ha.` without consulting the grant. That is the point: today's twelve
tools are easy to keep honest by hand; the thirteenth, added later by someone
who never read this file, is not.

---

## Recipes

A recipe is a list of steps: `start` → `fr` (fill) → `vc` (vacuum) → `pg`
(purge) → `bo` (brew-out), with `dialog` anywhere it needs to stop and ask.

Three rules that fail invisibly if you get them wrong, all reproduced from the
vendor app in `protocol/recipe.py`:

1. **Zero-valued size keys are dropped, not sent as `0`.** Absent and zero mean
   different things to the firmware.
2. **Everything is stringified.** The app sends `"205"`, never `205`.
3. **A manual-stop purge becomes a dialog**, and loses its pressure and time —
   because the app's own code reads them from the wrong object and never copies
   them. We match the app's *actual output*, not its intent.

### Serving sizes

One recipe carries up to three portions. The machine's own model; the app's
editors are laid out as serving 1 / 2 / 3, and brewing sends one.

Every vendor recipe differs between sizes by **fill volume alone** — 181/241/301
ml, 188/250/312 — which is medium ±25%. Temperature, vacuum and steep are
identical across the three, which follows from the dial-in convention: vacuum
sets concentration, steep sets intensity, so moving them between sizes would
serve a different drink rather than more of the same one.

`R.sizes_from()` derives all three through a *notional medium* rather than
size-to-size, because scaling small straight to large chains two roundings and
lands on 302 where the vendor says 301.

Storage keeps both: `rec["sizes"]` is the truth, `rec["steps"]` mirrors the
default size so every existing reader keeps working. Both are written through
`_set_sizes()` — one writer is what stops a mirrored field drifting.

---

## The document pipeline

See [DOCUMENTS.md](DOCUMENTS.md). In short: the corpus is **mostly pictures**
(620 of 717 pages), so the add-on renders them, describes them with a vision
model, and reads structured data back out.

---

## The browser UI

`addon/webroot/index.html` — one file, ~3,300 lines, no build step, no
dependencies. That is deliberate: it is served by a Python container to an
iframe inside Home Assistant, and a toolchain would be a second thing to
install, break and version.

Five `<script>` blocks, each an IIFE with its own scope. They share through
`window.bkon*` — `bkonMd`, `bkonCite`, `bkonFigure`, `bkonApplySteps`,
`bkonStudioSteps`. If you add a cross-block helper, follow that convention.

`tests/test_webroot.py` guards it structurally: every class rendered has a CSS
rule, every handler has an element **and** every element a handler, markup is
balanced, focus states exist, animations respect reduced motion.

**The failure it exists for**: Easy mode was toggled, persisted and re-rendered
while `render()` never read the flag — fully present, entirely disconnected. A
test asking whether `flowText()` existed passed. It now asks whether it is
*called*. Check things are connected, not that they exist.

Visual conventions are in [DESIGN.md](DESIGN.md).

---

## On the device

```
/share/bkon_lightrag/
    rag_storage/     LightRAG's graph + vector store
    originals/       the source PDFs and videos, + manifest.json
    figures/         rendered pages as PNG, + figures.json (captions, facts)
/data/kb.json        the passage index (rebuilt by /documents/reindex)
```

`/share` belongs to root and the add-on runs as root, which is why originals
arrive over an upload endpoint rather than a file copy.

---

## Building, testing, deploying

```bash
./tests/run_all.sh                 # 858 assertions, no dependencies, no network
python3 scripts/check_core_sync.py # vendored copy matches the integration
```

Tests import nothing outside the standard library. `tests/_bootstrap.py` stubs
enough of Home Assistant to import the integration's pure modules.

Releasing the add-on:

1. Bump `version:` in `addon/config.yaml` — **the Supervisor only sees a new
   version**, so a fix without a bump never reaches the device.
2. Add a `addon/CHANGELOG.md` entry.
3. Push. CI runs `tests`, `validate` and `addon` (a multi-arch image to GHCR).
4. Reload the store, then update the add-on.

`apparmor:` in `config.yaml` is a **boolean**. Setting it to a profile name made
the add-on invisible in the store for several releases; `tests/test_addon_config.py`
now checks it.

---

## Where the bodies are buried

- **Error codes are `(C:code M:module)`.** An earlier version rendered them
  inverted and a cross-check agreed with it because it shared the wrong
  assumption. Verified against the vendor's own labels and a photograph of the
  machine's display.
- **`wp` and `dst` never reach the wire.** They are in the app's data model and
  its built-in rinse recipe; `prepRecipe` discards them. Accepted so stored
  recipes round-trip, asserted in tests never to be transmitted.
- **A reindex must not enumerate the fields it keeps.** It once rebuilt each
  figure as `{doc, page, caption, label}` and silently destroyed `facts` — 616
  pages of vision output, deleted by a refresh. Carry prior state wholesale.
- **Extraction values are read off photographs by a model.** One misread a
  service phone number. Fields that disagree across sightings are kept as
  `variants` and reported as a disagreement rather than resolved.
- **A regexp that matches a substring anywhere is not an identifier lookup.**
  `V5` matched a power supply whose spec reads "208/230V50-60Hz".

---

## Still needs a real brewer

The recipe **wire form** (XML step-tags — well-evidenced from the binary, never
confirmed on hardware), the **dialog-response frame** (the `msg:3` lead), and
BLE **chunking**. `send_raw` is the test hook. This is the largest remaining
risk in the project: if the wire form is wrong, every brew fails, and no test
here can tell you. See
[PROTOCOL.md](PROTOCOL.md#what-still-needs-hardware-to-confirm).

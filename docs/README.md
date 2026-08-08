# BKON Brewer — project wiki

Everything this project is, in one place. It controls a BKON Craft Brewer from
Home Assistant, builds and tunes recipes in plain language, answers questions
from the machine's own documents, and does it all reverse-engineered from the
vendor app for hardware you own.

New here? Read **[How it fits together](#how-it-fits-together)**, then jump to
whatever you need.

---

## How it fits together

```
        You ─ voice / dashboard / service call
                       │
        ┌──────────────┴───────────────┐
        │   Home Assistant integration │   custom_components/bkon_brewer/
        │   entities · services · agent│
        └───────┬───────────────┬──────┘
                │ Bluetooth      │ HTTP (optional)
                ▼                ▼
         The brewer        LightRAG add-on ── Ollama / Anthropic / OpenAI
       (Nordic UART via     (local embeddings,   (generation)
        an ESPHome proxy)    graph retrieval)
```

- **Brewing** is local Bluetooth. Nothing about it needs the cloud.
- **Questions** use a built-in retriever by default; the optional add-on upgrades
  them to semantic answers written by a model you choose.
- **Recipes** live in Home Assistant's own store, exportable to git and to the
  machine's own menu-file format.

---

## Guides by task

| I want to… | Read |
|---|---|
| Understand the wire protocol | [PROTOCOL.md](PROTOCOL.md) |
| Understand the recipe format | [RECIPE_SCHEMA.md](RECIPE_SCHEMA.md) |
| Know the confirmed units & error codes | [INTEL.md](INTEL.md) |
| Set up semantic Q&A (LightRAG + a model) | [RAG.md](RAG.md) |
| Make recipes longer than Bluetooth allows | [LONGER_RECIPES.md](LONGER_RECIPES.md) |
| Understand the `.bbp` menu-file format | [BBP_FORMAT.md](BBP_FORMAT.md) |
| See how faithful this is to the app | [APP_COMPARISON.md](APP_COMPARISON.md) |
| Install the add-on | [../addon/DOCS.md](../addon/DOCS.md) |

---

## Entities

Set up in Home Assistant under one **BKON Brewer** device.

| Entity | Tells you |
|---|---|
| `sensor.*_status` | idle / brewing / waiting for operator / complete / error |
| `sensor.*_current_step` | which step of the brew is running |
| `sensor.*_dialog` | the brewer's outstanding prompt, if any |
| `sensor.*_last_error` | the last fault, in plain words |
| `sensor.*_recipe_library` | how many recipes, with each one's size |
| `button.*_abort` · `button.*_manual_purge` | one-tap actions |

## Services

**Brewing** — `brew`, `brew_saved`, `manual_purge`, `abort`, `respond_dialog`,
`send_raw` (developer escape hatch).

**Recipes (CRUD)** — `save_recipe`, `get_recipe`, `delete_recipe`,
`build_recipe`, `customize_recipe`.

**Files & git** — `export_recipes` / `import_recipes` (one JSON per recipe),
`download_recipes` (a readable .txt), `export_menu` (a machine menu file, for
[longer recipes](LONGER_RECIPES.md)).

**Concierge** — `ask` (a question or a recipe tweak), `lint_recipe` (check a
recipe before brewing), `diagnose` (an error code or symptom).

## The concierge

Ask in plain language, by voice through Assist or the `ask` service:

- *"make my Morning Cup stronger"* → tunes the recipe (vacuum + steep), previews
  the change ([advisor](../custom_components/bkon_brewer/advisor.py)).
- *"how do I descale?"* → answers from the machine's documents
  ([knowledge](../custom_components/bkon_brewer/knowledge.py)).
- *"what does C:3 M:5 mean?"* → cause and fix
  ([diagnostics](../custom_components/bkon_brewer/diagnostics.py)).

The routing that tells those apart lives in
[concierge.py](../custom_components/bkon_brewer/concierge.py).

---

## How it was built

The vendor's app is a Cordova/Vue app that shipped source maps, so its logic was
recoverable outright, not decompiled. The transport is Nordic UART; recipes are
XML step-tags in a `{msg:1:…}` frame. Facts (units, error codes) came from an
archive of the service portal. **No vendor application source or document text
is in this repository** — the document index is built locally and git-ignored.
See [APP_COMPARISON.md](APP_COMPARISON.md) for a fidelity audit.

## Testing

```
./tests/run_all.sh          # 316 assertions, no dependencies
```

The logic that matters — encoding, the advisor, retrieval, provider selection,
the recipe schema — is pure and tested. I/O layers are thin and clearly marked
where they are unverified against hardware.

## Still needs a real brewer

Some of the protocol is inferred from the binary and awaits a hardware capture:
the recipe **wire form** (well-evidenced), the **dialog-response frame** (the
`msg:3` lead), and BLE **chunking**. The `send_raw` service is the test hook.
Details in [PROTOCOL.md](PROTOCOL.md#what-still-needs-hardware-to-confirm).

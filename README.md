<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=Amantux&repository=bkon-brewer&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Add the BKON Brewer integration to HACS via My Home Assistant.">
  </a>
  <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FAmantux%2Fbkon-brewer">
    <img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Add the BKON Brewer add-on repository to your Home Assistant.">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/HACS-custom-41BDF5.svg" alt="HACS custom">
  <img src="https://img.shields.io/badge/Home%20Assistant-%E2%89%A5%202024.4.0-41BDF5.svg" alt="Min HA version">
  <img src="https://img.shields.io/badge/tests-324%20passing-3c8f54.svg" alt="324 tests passing">
  <img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0">
</p>

# BKON Craft Brewer ☕

Control a **BKON Craft Brewer** from Home Assistant over Bluetooth — brew,
build and tune recipes in plain language, and ask the machine's own manuals what
a fault means. Reverse-engineered from the vendor app, for hardware you own. No
cloud account, no vendor server; brewing is entirely local.

**[📖 Project wiki](docs/README.md)** — architecture, every service, recipes,
protocol, and status in one place.

> **Status:** built and unit-tested (324 assertions), **not yet hardware-tested**.
> The protocol was recovered from the vendor app; every unconfirmed decision is
> labelled in the code and docs. A **Simulate** mode lets you explore the whole
> interface with no brewer.

---

## Install

There are two pieces. You need the **integration**; the **add-on** is an optional
upgrade for smarter question-answering.

### 1. The integration (required) — via HACS

[![Open your Home Assistant instance and open the repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Amantux&repository=bkon-brewer&category=integration)

1. Click the badge above (or in HACS → **⋮** → *Custom repositories*, add
   `https://github.com/Amantux/bkon-brewer` as an **Integration**).
2. Install **BKON Craft Brewer**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → BKON Craft Brewer.** It
   discovers the brewer over Bluetooth, or tick **Simulate** to try it with no
   hardware.

<details>
<summary>Manual install (no HACS)</summary>

Copy `custom_components/bkon_brewer/` into your Home Assistant `config/custom_components/`
directory and restart.
</details>

### 2. The LightRAG add-on (optional) — semantic Q&A

[![Add the BKON Brewer add-on repository to your Home Assistant.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FAmantux%2Fbkon-brewer)

1. Click the badge (or **Settings → Add-ons → Add-on Store → ⋮ → Repositories**,
   add `https://github.com/Amantux/bkon-brewer`).
2. Install **BKON LightRAG**, set a service key and a generation provider
   (Ollama / Anthropic / OpenAI-compatible), and start it.
3. Point the integration at it in the integration's **Configure** dialog.

Without the add-on, questions are answered by a built-in keyword retriever — the
add-on upgrades them to semantic answers from a model you choose, and the
integration falls back automatically if it is unavailable. See
[docs/RAG.md](docs/RAG.md).

---

## What it does

- **Brew & control** — `brew`, `brew_saved`, `manual_purge`, `abort`,
  `respond_dialog`, all over local Bluetooth. Status, current step, dialog
  prompts and errors surface as sensors, updated on push.
- **Build & tune recipes** — start from a grounded template, then say
  *"stronger"* or *"less bitter"* and watch the vacuum and steep move
  (`build_recipe`, `customize_recipe`).
- **Ask the manuals** — *"How do I descale?"*, *"What's C:3 M:5?"* — answered from
  the brewer's own service documents (`ask`, `diagnose`).
- **Yours, in git** — recipes are files you can export, diff, commit and reload
  (`export_recipes` / `import_recipes`), or push to the machine's own menu format
  for [longer recipes](docs/LONGER_RECIPES.md).

The full service list and the concierge are in the **[wiki](docs/README.md)**.

## Requirements

- Home Assistant **2024.4.0** or newer.
- A **Bluetooth** adapter, or an **ESPHome Bluetooth proxy** in range of the
  brewer (the integration reaches the machine through whichever is available).
- For the add-on: a generation provider (a local Ollama, an Ollama Cloud key, an
  Anthropic key, or any OpenAI-compatible endpoint). Embeddings run locally.

## Testing

```bash
./tests/run_all.sh          # 324 assertions, no dependencies
```

The logic that matters — encoding, the advisor, retrieval, provider selection,
the recipe schema — is pure and tested. I/O layers are thin and clearly marked
where they are unverified against hardware.

## Docs

- **[Project wiki](docs/README.md)** — start here
- [Protocol](docs/PROTOCOL.md) · [Recipe schema](docs/RECIPE_SCHEMA.md) ·
  [Confirmed intel](docs/INTEL.md)
- [Semantic Q&A](docs/RAG.md) · [Longer recipes](docs/LONGER_RECIPES.md) ·
  [`.bbp` menu format](docs/BBP_FORMAT.md) · [Fidelity audit](docs/APP_COMPARISON.md)
- [Add-on setup](addon/DOCS.md)

## Provenance & licence

Reverse-engineered for interoperability with hardware the owner possesses. **No
vendor application source or document text is in this repository** — the document
index is built locally and git-ignored; facts (units, error codes) are folded in
from the owner's own service-portal archive. Licensed **AGPL-3.0**.

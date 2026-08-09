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
  <img src="https://img.shields.io/badge/tests-496%20passing-3c8f54.svg" alt="496 tests passing">
  <img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0">
</p>

# BKON Craft Brewer ☕

Control a **BKON Craft Brewer** from Home Assistant over Bluetooth — brew,
build and tune recipes in plain language, and ask the machine's own manuals what
a fault means. Reverse-engineered from the vendor app, for hardware you own. No
cloud account, no vendor server; brewing is entirely local.

**[📖 Project wiki](docs/README.md)** — architecture, every service, recipes,
protocol, and status in one place.

> **Status:** built and unit-tested (496 assertions), **not yet hardware-tested**.
> The protocol was recovered from the vendor app; every unconfirmed decision is
> labelled in the code and docs. A **Simulate** mode lets you explore the whole
> interface with no brewer.

---

## Install

Two pieces, installed separately. Take them in order.

| | What it gives you | Needed? |
|---|---|---|
| **1. Integration** | Brewing over Bluetooth, entities, services, voice | **Yes** — this is the brewer control |
| **2. Add-on** | The **Recipe Studio** (visual builder + chat + scoring) and semantic Q&A | Optional, but it's where the good stuff lives |

### 1. The integration — via HACS

[![Open your Home Assistant instance and open the repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Amantux&repository=bkon-brewer&category=integration)

1. Click the badge ⬆️ — or in HACS → **⋮** → *Custom repositories*, add
   `https://github.com/Amantux/bkon-brewer` with category **Integration**.
2. Install **BKON Craft Brewer**, then **restart Home Assistant**. (The restart
   is required; the integration will not appear until you do.)
3. **Settings → Devices & Services → + Add Integration →** search
   *BKON Craft Brewer*.
4. It looks for the brewer over Bluetooth. **No brewer yet?** Tick **Simulate**
   — every entity, button and service works against a scripted brewer.

✅ **You should now see** a *BKON Brewer* device with 5 sensors and 2 buttons.

<details>
<summary>Manual install, without HACS</summary>

Copy `custom_components/bkon_brewer/` into your Home Assistant's
`config/custom_components/` directory, then restart Home Assistant.
</details>

### 2. The add-on — the Recipe Studio

[![Add the BKON Brewer add-on repository to your Home Assistant.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FAmantux%2Fbkon-brewer)

1. Click the badge ⬆️ — or **Settings → Add-ons → Add-on Store → ⋮ →
   Repositories**, and add `https://github.com/Amantux/bkon-brewer`.
2. Find **BKON LightRAG** in the store list and click **Install**. (It pulls a
   prebuilt image for `amd64` and `aarch64` — including **Home Assistant
   Yellow** and Raspberry Pi — so there is nothing to compile.)
3. Open the **Configuration** tab and set your generation provider — see
   [below](#choosing-a-provider). This is the one step people miss.
4. **Start** the add-on, and turn on **Show in sidebar**.

✅ **You should now see** a **Bkon RAIN** entry in the sidebar. Open it for the
wiki and the **Recipe Studio**.

5. *(Optional)* To let the integration use the add-on for questions too, point
   it at the add-on in the integration's **Configure** dialog.

#### Choosing a provider

The chat, the recipe scoring and semantic answers all need a model. Pick one in
the add-on's **Configuration** tab:

| `ai_provider` | Set | Notes |
|---|---|---|
| `ollama` | `base_url` → `http://<host>:11434`, `model` | A local Ollama. No key, nothing leaves your network. |
| `ollama` | `api_key`, `model` (leave `base_url` empty) | Ollama **Cloud** — good on a Pi that can't run a model locally. |
| `anthropic` | `api_key`, `model` | e.g. `claude-sonnet-5`. |
| `openai` | `api_key`, `model`, optional `base_url` | Any OpenAI-compatible endpoint. |

**Without a provider** the add-on still starts and serves the wiki and the
visual recipe builder — only the chat and scoring are unavailable, and they say
so plainly rather than failing silently.

#### What the LightRAG toggle does

LightRAG ships **inside every build**, embedding model included, and is **on by
default** — nothing extra to install. Turn `enable_lightrag` **off** to run the
Recipe Studio alone: it starts faster and uses less memory, the chat still
builds, tunes, lints, diagnoses and scores, and only *"how do I descale?"*-style
document questions go away (the integration falls back to its built-in keyword
retriever). See [docs/RAG.md](docs/RAG.md).

### Something not working?

| Symptom | Cause |
|---|---|
| Add-on missing from the store | Refresh the store (**⋮ → Check for updates**). If it's still absent, the Supervisor rejected `config.yaml` — check **Settings → System → Logs → Supervisor**. |
| Add-on installs but the sidebar entry is missing | Turn on **Show in sidebar** on the add-on page. |
| Chat/score say "no generation provider" | Set a provider and key in the add-on **Configuration**, then restart it. |
| Integration missing after HACS install | Restart Home Assistant. |

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
./tests/run_all.sh          # 496 assertions, no dependencies
```

The logic that matters — encoding, the advisor, retrieval, provider selection,
the recipe schema — is pure and tested. I/O layers are thin and clearly marked
where they are unverified against hardware.

## Docs

- **[Project wiki](docs/README.md)** — start here
- [Dashboard card](dashboard/lovelace-card.yaml) — paste-in Lovelace card
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

# Changelog

## 0.9.1
- **The tasting journal is now readable by MCP, automations and voice.** It was
  living only in the browser, where nothing else could see it. It is stored on
  the recipe in Home Assistant and exposed on the **recipe library sensor's
  attributes**, so any MCP client reading that entity gets the whole
  change → flavour history without a new integration surface.
- New **`bkon_brewer.add_tasting_note`** service so MCP, an automation or the
  studio can all write to the *same* journal — it is only useful as one history.
- **Saving from the studio publishes its journal** to Home Assistant, which is
  what makes it visible to everything else. Journals are capped at 20 entries so
  a sensor attribute cannot bloat the state machine.

## 0.9.0 — the studio comes first
- **Reorganised around the studio.** It is now the landing page, with
  **Diagnose** and **Settings** beside it; the whole wiki moved behind one
  collapsible **Wiki & reference** group.
- **Mobile and touch friendly.** A top bar with a slide-out drawer under 800px,
  a scrim and Escape to dismiss, and finger-sized controls everywhere — 40–44px
  targets, 16px inputs (so iOS stops zooming on focus), and a step grid that
  reflows. Coarse-pointer devices get the larger targets at any width.
- **The recipe creation and recipe store areas are called out** as distinct
  panels with their own colour rail, rather than blending into the page.
- **The embedded studio chat is gone.** The floating companion replaces it, and
  it now **sees the page you are on** — on the studio that means the live recipe
  and its tasting journal, so a suggestion is about the cup in front of you. When
  it changes the recipe, the change lands in the builder instead of being
  described.
- **A tasting journal.** Save a change with a note and it records what moved
  (temperature, vacuum, steep, fill…) next to how it tasted. Ask *"what made it
  less bitter?"* and the assistant reads that history — the machine knows what
  changed, you know how it tasted, and the journal is where the two meet.
- **Settings page**: what the assistant actually has — provider, model, document
  Q&A — and where to change it. It asks the service *whether* a key is set, never
  what it is.
- **Diagnosis agent**: the confirmed fault table first, then the machine's own
  documents through LightRAG, with the likely cause and the next thing to try.

## 0.8.1
- `export_bbp` now runs each recipe through `prepare()` before writing, so the
  exported portions carry a brew-out and the wire rules — running the export for
  real showed portions with **no brew-out at all**, which no device file has.
- The four bundled default recipes used a purge pressure of 50, from before the
  app's own validator was read; the accepted band is 25–35. They now use 30.

## 0.8.0
- **A recipe library in the studio.** Save, list, load, update and delete
  recipes without leaving the page — they persist in the browser, so the studio
  is somewhere you keep work rather than a scratchpad you lose on refresh. Home
  Assistant's library stays the source of truth for brewing; **Save recipe**
  still copies the service call for it.
- **`.bbp` export** via the new `bkon_brewer.export_bbp` service —
  **experimental**, and labelled as such everywhere. The container checksum and
  step records are confirmed and round-trip exactly; the category framing is
  inferred and has never been accepted by a machine.

## 0.7.3
- **Save and Send moved to the bottom of the studio**, as a full-width action
  bar under the builder rather than buried in the side panel. **Save** copies a
  `save_recipe` call (steps, rating and notes); **Send** copies a `brew_saved`
  call for a recipe already in the library.

## 0.7.2
- **A floating chat companion on every page**, bottom-right, in the Edibl style —
  the same tool-using brain as the studio chat, reachable from the wiki, with
  suggestion chips and Escape-to-close.
- **New `GET /config`**: the UI reads the model's state once and adapts, instead
  of firing a request and making you interpret a failure. When no provider is
  set, the companion says exactly what to change and points at the recipe
  builder, which needs no model. Carries no secrets — whether a key is set,
  never the key.

## 0.7.1
- **Fixes the add-on being missing from the add-on store.** `apparmor:` takes a
  boolean, not a profile name; the string made the Supervisor refuse the whole
  config, so the repository resolved but offered nothing to install. Present
  since 0.4.0.
- **A misconfigured provider no longer takes the add-on down.** Choosing
  Anthropic or OpenAI without a key used to raise during startup and crash-loop
  the container. Now the wiki and the recipe builder still load, and chat and
  scoring return a clear reason instead.
- **The embedding model is baked into the image**, so LightRAG works on first
  start with no download — and on a machine with no internet at all.
- Fixed the add-on's documentation link (it pointed at a path that never existed).

## 0.7.0
- **Score a recipe** in the studio: a "Score recipe" button and a `score_recipe`
  chat tool ask the model to rate the current recipe out of 100 and comment on
  it — grounded in the objective facts (byte fit, linter findings, the confirmed
  ranges and vacuum relationships) so the critique is about the recipe, not
  vibes. New `POST /score` endpoint; needs a generation provider.
- **Your own rating and notes** now persist on a recipe. Star it and jot a note
  in the studio, and they ride along with the copied `save_recipe` call; a new
  `rate_recipe` service (and optional `rating`/`notes` on `save_recipe`) stores
  them. Feedback survives an edit and round-trips through export/import.

## 0.6.0
- **Document Q&A is now a toggle** (`enable_lightrag`, on by default). Off, the
  same container serves the wiki and the recipe studio alone: the chat still
  builds, tunes, lints and diagnoses, and startup skips the embedding model and
  graph storage entirely. The documents tool is then absent from the chat rather
  than present and failing, and `/query` answers 501. Existing installs are
  unaffected — the default keeps today's behaviour.
- **Recipe studio** in the ingress panel: a hand-builder paired with a chat that
  shares the same recipe. Ask *"a strong small cup, less bitter"* and the steps
  change; the chat drives the same build / tune / lint / diagnose tools the
  integration ships, and answers how-to questions from the machine's documents.
- New `POST /chat` endpoint: one tool-using turn, provider-agnostic (Ollama /
  Anthropic / OpenAI-compatible) via JSON tool-calling, no vendor tool API. The
  recipe logic is the integration's own, vendored into the add-on so it builds
  standalone and kept in sync by CI.

## 0.5.0
- Ingress now serves the project wiki (BKON RAG panel) instead of a bare status
  page: a readable, self-contained UI in the Home Assistant sidebar, matching
  how the sibling add-ons serve a webroot. The key-guarded API is unchanged.

## 0.4.0
- Home Assistant ingress: a status page in the sidebar (BKON RAG panel),
  authenticated by HA. The key-guarded API stays reachable on port 9621 for the
  integration.
- AppArmor profile (`bkon_lightrag`): least-privilege confinement matching the
  sibling add-ons — file I/O and the network the service needs, everything else
  default-denied. No privilege drop or Supervisor access, which this service
  does not need.
- Debian slim base via `build.yaml`, matching Edibl / HomeHoard / myMeal. Fixes
  reliable aarch64 wheels for onnxruntime and numpy (the local embedder).

## 0.3.0
- Pluggable generation provider: Ollama (local or Cloud), Anthropic, or any
  OpenAI-compatible endpoint, selected by config. Per-provider namespaced keys;
  SSRF-guarded base URLs.

## 0.2.0
- Self-contained service: local bundled embeddings + cloud generation.

## 0.1.0
- Initial LightRAG service for the BKON concierge.

# Changelog

## 0.16.0
- **The studio's store is now a shortlist, not the whole library.** It shows up
  to five recipes worth starting from — ranked by whether you rated it, how
  often you brew it, and how recently you touched it — each labelled with *why*
  it is there (`5★ rated`, `brewed 6×`, `remux`, `recent`, `editing`). The full
  library is a click away on **Recipes**.
- **Drag to reorder actually feels like dragging.** The card lifts and tracks
  the pointer with no transition (easing there reads as lag), the others slide
  out of the way, and a dashed space shows exactly where it will land. Nothing
  commits until you let go, and the moved card settles so the eye can follow it.
- **Remux from the studio**, not just the Recipes page — fork whatever is on
  screen. A remux stays unsaved and clearly marked, can be renamed before
  promoting, and **promoting under the parent's name is refused** rather than
  quietly overwriting the recipe the remux exists to leave alone. **Discard**
  drops it and returns you to the original.

## 0.15.0
- **Fixes Export .bbp.** The panel runs inside Home Assistant's ingress iframe,
  and a sandboxed iframe cannot start a download — the click was swallowed with
  no error at all. The integration now writes the file and the panel opens it at
  `/local/bkon/hamenu.bbp`, an ordinary top-level navigation that downloads
  normally.
- **Score, tasting journal and the readout moved below the builder.** Building
  is the task; those panels are what you consult after a change, not while
  making one. They flow into columns when there is room.
- **The tasting journal now shows brews alongside tastings** on one timeline —
  what you changed and how it tasted, next to when it was actually brewed. It
  carries a remux's lineage, the brew count, and a single derived line naming
  which change your best- and worst-rated versions followed. Deliberately one
  line: anything cleverer would be reading patterns into three data points.

## 0.14.1
- **Brings the recipe builder back.** The wiki switches pages with
  `section{display:none}`, and the 0.9.0 restructure made the builder and the
  recipe store `<section class="zone">` — so the page rule hid them both. They
  were in the markup, and the script rendered into them, but they were never
  displayed. The rule is now scoped to `main > section`, which is the pages, and
  a nested section can no longer be caught by it.
- Adds a structural test over the served page: no script may reference an
  element that does not exist, the page rule must stay scoped, the builder and
  store must be inside the studio page, every nav target must resolve, and the
  markup must balance.

## 0.14.0 — answers you can check
- **Ask the docs**: a surface for questions answered from the machine's own
  service and training documents, with the documents the answer came from listed
  underneath and an excerpt from each.
- **Citations are looked up, not written.** LightRAG produces the prose; the
  passage index says where it came from. Keeping those separate means the model
  cannot invent a source that does not exist. A few documents map onto a wiki
  page that already summarises them and link there; the rest are named but not
  linked, because inventing a destination is worse than not having one.
- Deliberately modest: sources are the documents the retriever matched, not
  per-sentence footnotes — enough to check an answer without claiming a
  precision the retrieval does not have.
- New `POST /ask` and `POST /documents/index`. With no model configured, or if
  generation fails, it still answers from the indexed passages directly and says
  that is what happened.

## 0.13.4
- The sidebar panel is now **Bkon RAIN** — RAIN is the brewing method the machine
  is built around, which is a better name for the thing than the retrieval
  technology behind one of its features.

## 0.13.3
- **The page no longer caches.** It shipped only an ETag and no `Cache-Control`,
  so a browser was free to keep serving a heuristically-cached copy — meaning an
  add-on update could land while you still saw the previous build, bugs and all,
  with no way to tell. It now revalidates on every load.
- **A visible build stamp** under the sidebar title, so *"which version am I
  looking at"* is answerable from the page rather than inferred.

## 0.13.2
- **Fixes the studio being half-dead.** Handlers for the embedded chat removed
  back in 0.9.0 were still in the script and called `addEventListener` on an
  element that no longer existed. That threw, and everything below it never ran
  — including the first render, loading your saved recipes, and syncing with
  Home Assistant. The builder looked present but could not really be used.
- **Settings now goes provider → base URL → key → model**, which is the order
  the dependencies actually run in, and **Fetch models** lists what the provider
  really has so you pick one instead of typing it from memory. Changing provider
  clears the list, because it belonged to the previous one.

## 0.13.1
- **Just start building.** The describe box sat at the top of the builder, which
  made writing a sentence feel like step one. Building is the primary path now:
  the step palette comes first, with **＋ Blank recipe** and one-tap bases
  (Coffee, Green tea, Black tea, Delicate) beside it. Describing it in words is
  still there, folded under *"…or describe it in words"*.
- The one-tap bases run through the same compiler as a typed description, so a
  tapped start and a described one produce the same recipe rather than two rival
  definitions of "a coffee".

## 0.13.0 — a library you can browse
- **A Recipes view**: every recipe as a card you can scroll, search and sort by
  name, rating, times brewed or score. Each card carries its score, stars, brew
  count and a colour bar of its step sequence — the shape of a recipe at a
  glance, which is what a photo does for a food recipe and what a brew has
  instead.
- **Remux**: fork any recipe into the builder as `… v2`. The original is never
  touched, and the copy records where it came from, so a variant has visible
  lineage rather than being an unexplained near-duplicate.
- **Promote**: a remux stays unsaved and clearly marked until you promote it,
  at which point it becomes its own recipe — in Home Assistant too.
- **Score from the card.** Scores are cached per recipe, so browsing the library
  does not re-run a model call for every tile.

## 0.12.0 — manage the brewer without leaving the studio
- **Save, delete and brew now actually happen.** The studio used to hand you a
  YAML service call to paste into Developer Tools; with `homeassistant_api`
  enabled the add-on calls the service itself. **Send to brewer** brews.
- **The recipe store is Home Assistant's library**, read off the sensor it
  already publishes — so the studio, voice, automations and MCP all see one set
  of recipes, with ratings, notes, journal and brew count.
- Still works standalone: if Home Assistant is unreachable the browser store
  takes over and the buttons fall back to copying the call, saying so plainly.
- New endpoints: `GET /recipes`, `POST /recipes`, `/recipes/delete`,
  `/recipes/brew`, `/recipes/note`.

> **Note:** this release turns on `homeassistant_api`, so the add-on can call
> Home Assistant services. That is what makes the studio able to act rather than
> only describe.

## 0.11.0
- **`/documents/text` no longer lies.** LightRAG extracts entities through the
  model, so an insert fails when the provider does — the endpoint used to answer
  `inserted` regardless, which made a whole ingest look successful while
  indexing nothing. It now verifies the document actually landed and says so
  when it did not.
- **Brew history.** Every `brew_saved` records that it ran, with a count and a
  last-brewed time on the library sensor, so the tasting journal's intent can be
  correlated against what was actually brewed.
- **A dashboard card** (`dashboard/lovelace-card.yaml`): status, current step,
  brew buttons, abort and manual purge, and a dialog prompt with Continue and
  Cancel that appears only while the brewer is actually waiting.
- **`list_templates` now reports the compiler's styles** rather than the four
  retired fixed templates.

## 0.10.1 — validation while you build
- **Problems now show as you build**, not at save time. The panel under the byte
  gauge lists every finding with its fix, updating as you edit.
- **New ordering checks**, because each step can be valid and the sequence still
  wrong: extracting before any water is added (an error — a vacuum on an empty
  chamber), a Start that is not first, more than one Start, a recipe ending on a
  Dialog, and more total water than a chamber is likely to hold.
- Validation runs on the server through the same Python the brewer goes through,
  so there is one implementation of the rules rather than a JavaScript copy that
  can drift. New `POST /lint`; no model needed.

## 0.10.0 — describe the drink, get the recipe
- **Natural language to a recipe, with targeting.** Say *"a strong small green
  tea at 185F, two vacuums, 8 second steep"* and it builds exactly that. It reads
  the beverage, the size, the strength, and any hard numbers, then constructs the
  steps to hit them.
- Grounded in the published base recipes: green tea starts 175 °F / 24 kPa and
  black 205 °F / 20 kPa (so a hotter brew starts from a *shallower* vacuum),
  multi-vacuum sequences follow X, X+2, X+1, and delicate leaf gets one vacuum
  with front-loaded water.
- **Numbers the machine cannot do are clamped and said**, never silently
  accepted — ask for 260 °F and you get 212 °F plus a note explaining why.
- A **Compose** box at the top of the builder. It is deterministic and needs no
  model, so describing a drink works whether or not a provider is configured.
  New `POST /compose`; the same compiler backs the `build_recipe` service and the
  assistant's tool, so all three agree.

## 0.9.3
- **Drag to reorder steps**, with a grip on each card. Built on Pointer Events,
  so mouse, pen and touch take one code path, and `touch-action:none` on the grip
  stops the page scrolling out from under a drag in progress. The grip is
  40×44px on touch. The arrow buttons remain, so reordering is still possible
  by keyboard.
- **Export .bbp** button in the studio: downloads the whole store as the
  machine's own menu-file format. Built server-side by the confirmed encoder,
  with the brew-out appended and the wire rules applied. Still **experimental** —
  the response carries an `X-Bkon-Experimental` header saying so, and the button
  links to the format notes.

## 0.9.2
- **Fixes the builder on mobile.** A pre-drawer rule still carried
  `position:static!important`, which beat the new drawer's `position:fixed` while
  its `transform` still applied — so the nav sat in the page flow, shifted
  invisibly off-screen, pushing everything down and leaving a drawer that could
  never open. The obsolete rule is gone and the builder's own grid now collapses
  at the same breakpoint as the rest of the page.
- **Set the provider, model and API key from the Settings page.** Reaching the
  add-on's Configuration tab is awkward on a phone, and a key you cannot set is a
  feature you cannot use. Changes apply immediately, with no restart. Settings
  saved here win over the add-on options; the key is stored in the add-on's own
  data volume and is never sent back to the page — leaving the field blank keeps
  the saved one.

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

# Changelog

## 0.23.5 — the status page can name your model again
- **"Model: using the provider default"** was shown no matter what you had set.
  The status page read a `model` attribute the providers never had — they keep
  it privately — so it always came back empty. All three now report it.
- **And it says when two settings disagree.** The model saved in this UI
  overrides the one in the add-on's Configuration tab, silently. If yours
  differ, Settings now says which is winning and how to go back — the failure
  this prevents is changing the model in Configuration, seeing no difference,
  and concluding the add-on is broken.

## 0.23.4 — an empty turn is retried, not failed
- **`think: false` was not the whole answer.** With reasoning suppressed,
  gpt-oss sometimes returns a completely empty turn — reasoning finished,
  nothing written, `done_reason: stop` — which surfaced as a 502. It is
  intermittent: the same prompt succeeds on a retry. So an empty response is
  now asked again, up to three times, and each attempt asks a *different* way
  (thinking off, then thinking back on) rather than repeating a question that
  already failed. Only if all three come back empty does it error — and it then
  says what would actually fix it: use a model that answers directly.

## 0.23.3 — it was sending the example back
- **`<your message to the user>` as a reply.** The prompt showed the answer
  shape with an angle-bracket placeholder, and the model sometimes echoed it
  verbatim. The examples are now worked ones — a real tool call, a real sentence
  — and an angle-bracketed stub is caught and retried rather than rendered,
  because a placeholder on screen looks like the app produced it.

## 0.23.2 — ask the model not to think out loud
- **Fixes 0.23.1's fix.** Reading `thinking` when `content` was empty stopped
  the blank bubbles, but it put the model's raw deliberation on screen — *"The
  user says: list my saved recipes. That's a direct tool call."* — which is
  worse than an error, because it looks like an answer. The root fix is to stop
  the reasoning instead: the Ollama call now sends `think: false`, so the answer
  lands in `content` where every other provider puts it. A model that rejects
  the parameter is simply asked again without it.
- Deliberation is still mined, but only for JSON. If the model wrote the tool
  call into its thinking, that is taken; prose is not.

## 0.23.1 — the assistant stopped answering; here is why
- **A blank reply on anything that needed a tool.** Simple questions worked, so
  the provider looked fine, but *"list my saved recipes"* returned an empty
  bubble every time. The cause: reasoning models (gpt-oss, deepseek-r1, qwen3)
  split their output — deliberation into `thinking`, the conclusion into
  `content` — and when the model reasons its way to a tool call without writing
  a conclusion, `content` is empty and the JSON we asked for is sitting in
  `thinking`, unread. The adapter now reads it.
- **And a blank is never rendered again.** The loop retries once, and if the
  model truly says nothing it says so — naming any tools that did run — rather
  than showing an empty bubble that is indistinguishable from a crash. All three
  providers now raise instead of returning `""`, so a silent model reads as a
  problem with the model rather than a problem with the app.

## 0.23.0 — it asks before it touches your machine
- **Nothing reaches Home Assistant unasked — reads included.** The assistant
  could already only *ask* to save or brew, but it listed and opened your
  recipes freely. Now the first time it wants to look, you get a chip: *Let the
  assistant read your recipe library?* Allowing lasts for that conversation and
  is never written to storage, because a permission that outlives the
  conversation it was granted in is one nobody remembers giving. The server
  accepts exactly four actions, all `bkon_brewer`, so a model talked into
  something cannot reach the rest of Home Assistant.
- **The guard is enforced by a test, not by care.** The real risk was never
  today's four tools — it was the fifth one, added later by someone who did not
  know the rule. `tests/test_ha_permission.py` walks the source: any tool that
  mentions `ha.` and does not consult the grant fails the build. Adding an
  ungated tool now breaks CI rather than shipping quietly.
- **It tells you what it is doing while it does it.** A tool-using turn can run
  half a minute behind a motionless "…", which reads as *stuck* rather than
  *slow*. The bubble now says *reading the manuals*, *tuning the recipe*,
  *scoring it*. Purely cosmetic by construction: if the progress channel fails,
  the turn carries on and only the wording is lost.

## 0.22.0 — the assistant grows up
- **Replies are formatted.** The companion rendered raw text, so a list arrived
  as run-on prose and `**24 kPa**` showed its asterisks. It now uses the same
  Markdown renderer the Diagnose page does — one renderer, not two that drift.
- **It knows the machine.** Its instructions carried no domain knowledge at all
  — the words *vacuum* and *kPa* did not appear. It now holds the confirmed
  facts: vacuum sets concentration and steep sets intensity, the ±2 kPa / ±5 s
  dial-in convention, the base recipes, the accepted ranges. 353 characters of
  instruction became 2,594.
- **It uses tables**, and is told to sort them by whatever actually helps and to
  say what it sorted by.
- **It can reach your recipes** — list them, open one — and it can *ask* to save
  or brew. Those two never happen on the model's say-so: they come back as a
  chip you answer. The server accepts exactly two actions, both `bkon_brewer`,
  so a model talked into something cannot reach the rest of Home Assistant.
- **Undo.** When a tool rewrites your recipe, the message that did it carries a
  button to put it back.

## 0.21.0 — Easy mode
- **A slider for every number, and a plain reading of what it means.** "24 kPa"
  tells you nothing without a feel for the range, so Easy mode turns the numeric
  fields into sliders and says what the current position amounts to — *standard
  — where the base recipes sit*, *deep — more concentration*, *outside the 25–35
  the app accepts*. The readings come from the documented base recipes, and a
  value the machine will not take says so rather than being given a flattering
  description.
- **Every step now says what it does**, built from its own current values: what
  a fill pours and steeps, what a vacuum pulls and holds, and for a purge —
  pressure, hold, delay and rinse — that it separates the grounds from the
  liquid, and that detection watches the pressure and stops when it reads done.
- The purge wording follows the Service Manual, which describes the pressure as
  a depth held for a time. Where the documents are silent — the delay's exact
  place in the sequence — the sentence describes it without claiming an order.
- Easy mode is remembered between visits.

## 0.20.1
- **Start is no longer in the step palette**, matching the vendor app, which
  treats it as structural and never lets you add one. Offering it is how a
  recipe ended up with two by accident. A blank recipe is seeded with a Start so
  you can still set a temperature.
- **A later temperature step is now called what it is.** A `start` after the
  first is not a second beginning, it is a change of setpoint, and it renders as
  **Change temperature**. It is offered as a separate, dashed palette item
  marked *unverified*: real device menus almost never contain one (108 of 111
  portions have exactly one setpoint), and nothing confirms the machine acts on
  a change part-way through a brew.
- The linter now says that plainly instead of asserting an outcome. It used to
  claim "only the temperature of one of them will be what you get" — which
  nobody has ever watched happen.

## 0.20.0
- **Fixes four ways the UI could get stuck.** Page switching used a bare
  `section` selector, so navigating anywhere hid the floating assistant while
  leaving its button hidden too — it was unreachable until you reloaded. The
  toast hid with opacity alone, leaving an invisible pill permanently swallowing
  taps across the bottom of the screen. Nav items were links without an `href`,
  so nothing in the navigation could be reached by keyboard or announced by a
  screen reader. And **Copy call** silently did nothing on a plain-HTTP Home
  Assistant, because optional chaining on an undefined clipboard API
  short-circuits the whole chain — no copy, no error, no message; it now falls
  back to a selection copy and finally to showing you the text.
- **Fixes the "describe it in words" form**, which had no handler at all.
  Pressing Compose submitted it as a GET, reloading the studio inside the ingress
  iframe and discarding the open recipe.
- Removes ~70 lines of stylesheet duplicated inside a 600px media query, which
  also trapped a rule meant for 800px — the document reader never went
  full-bleed between 601 and 800px.
- **Purge pressure is kilopascals**, confirmed from two independent documents and
  struck from the list of things needing hardware.

- **The studio had ten buttons and no answer to "what do I press?".** Save,
  Save to store, New, Blank recipe, Score, Promote, Discard, Copy call, Send,
  Remux and Export .bbp all sat at the same weight, so none of them read as the
  thing you normally do. There is one filled button now — **Save recipe** — with
  Send to brewer and Remux beside it as plain buttons, and that is the whole bar.
- **Copy call moved behind a disclosure.** It made sense when Save handed you
  YAML to paste; Save has actually written to Home Assistant since 0.14, so
  copying the call is now a scripting and debugging convenience, not a step in
  the normal path. It still works, one click further away.
- **Export .bbp moved to the Recipes page.** It exports the *whole library*, not
  the recipe you have open, so it never belonged next to actions that operate on
  the current recipe — and it is experimental enough that it should not be one
  slip of the thumb from Save. The warning about the format travels with it.
- **"Blank recipe" and "New" were the same button in two places.** Blank recipe
  stays, in the builder where you start; New is gone. Its function survives —
  discarding a remux with no parent still falls back to it.
- **The builder comes first now.** The saved-recipe shortlist was the first thing
  on the page, which said the studio is somewhere you *retrieve* recipes. It is
  somewhere you *build* them. The shortlist is a quiet strip underneath, using
  the small uppercase label the stylesheet already had for it.
- **Nineteen font sizes became seven, thirteen corner radii became four**, as
  `--fs-xs … --fs-3xl` and `--r-chip / --r-control / --r-card / --r-pill`. Having
  9.5, 10 and 10.5 px all in play is not a hierarchy, it is drift — each new
  element was a fresh guess and nothing lined up with anything. `--fs-xl` is
  16px on purpose: that is the threshold under which mobile Safari zooms a
  focused input, so touch form fields land on a real token instead of a
  hand-written exception.
- **Emoji are out of the section headings** and stay in the left nav. In the nav
  they are targets you scan for; in an `<h2>` they were decoration competing with
  the words. Weight and spacing carry the hierarchy.

## 0.19.0
- **Training videos are indexed alongside the documents**, via
  `scripts/build_video_index.py`, which reads the `*.info.json` yt-dlp writes.
  They go into the same index and the same retriever — one place to search, not
  a second path for video.
- **A video citation links out.** Passages can now carry a source URL, so a
  video source shows **Watch ↗** instead of *Read*. Documents have no link
  because the PDFs are not on the device and are not ours to serve; that is
  precisely why the field is optional rather than assumed.
- Transcripts are supported with `--captions`, but YouTube signs caption URLs
  with an expiry, so the ones recorded in an old archive return 404. Re-run
  yt-dlp against the live video to get fresh ones; the script handles both.

## 0.18.0
- **LightRAG's own "References" block is stripped.** It listed internal
  retrieval artefacts — *(Knowledge Graph)*, *(Document Chunks 1‑8)* — that
  nobody can open, directly above the real citations. The inline `[1]` markers
  pointing at it go too. A section genuinely written about sources is left alone.
- **Tables render as tables.** Troubleshooting matrices arrived as raw pipes;
  they are now proper tables that scroll sideways on a phone instead of breaking
  the page, with `<br>` inside cells honoured.
- **Suggestions disappear once you ask something** — a way in, not a fixture
  above the conversation.
- **Read opens a real reader**: a full overlay, dismissible with Escape or a
  click outside, that **lands on the page the citation came from** rather than
  page one of thirty.

## 0.17.1
- **A manual rinse**, `bkon_brewer.manual_rinse` — the app offers one and this
  did not. It is sent the way the app sends it: as a whole three-step recipe
  from the vendor's own source, not as a command like the purge.
- Documented two `start` fields nobody had seen: `wp` (water port) and `dst`
  (direct start). Both appear in the app's built-in rinse and **never reach the
  wire** — its own send path discards them, and so does ours. Asserted in the
  tests so a future "helpful" change cannot start transmitting them.

## 0.17.0 — one place for faults and manuals
- **Recipes and Diagnose no longer open the wiki group.** They are top-level
  pages; the nav only knew about three of them, so the rest were treated as wiki
  entries.
- **Ask the docs and Diagnose are now one chat: Diagnose & docs.** Diagnose ran
  through the recipe agent and was returning empty replies; both now use the
  document-grounded path, which works and returns its sources. Multi-turn, so a
  follow-up is answered in context.
- **Answers are formatted properly** — headings, lists, bold and inline code
  rendered rather than shown as raw Markdown.
- **Citations you can actually read.** Each source shows the document, the page
  and an excerpt, with **Read** opening its full indexed text in place. The PDFs
  are not on the device and are not ours to serve, so the link is to the text the
  answer was drawn from.
- The floating companion is unchanged: it stays the recipe agent, without
  citations, as asked.

## 0.16.1
- **Fixes the visual glitch when dragging a step to the top.** The dashed
  landing space was a flow element, so moving it re-laid-out the list on top of
  the transforms already shifting the cards — everything was displaced twice,
  and worst at the top where the space travelled furthest. It is now positioned
  out of flow and only marks the slot; the transforms alone open it.

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

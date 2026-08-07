# App vs. integration — a fidelity audit

A run-through of how the vendor app behaves, recovered from its source and
binary, against how this integration handles the same things. The point is to
find where the two diverge, and to be honest about what is confirmed versus
inferred.

## Faithful — matches the app

| Area | App | Integration |
|---|---|---|
| Transport framing | `{msg:1:<PAYLOAD>}` (ABORT/CANCEL/commands) | `frame()` produces the same |
| Abort / cancel | `{msg:1:<ABORT></ABORT>}` | `R.ABORT` byte-identical |
| Manual purge | `sendCommand("<PG><PS>50</PS>…")` — XML direct | `manual_purge` / `send_raw` send the same XML, framed |
| `prepRecipe` rules | drop zero-valued size keys; `manstop`→dialog; append `bo` bt=4; URL-encode dialog text; rebuild `start` with a rounded `tmp` | reproduced exactly, tested against the app's own purge literal |
| Recipe schema | nested object, `sequences.portions[]`, `purgedet`/`purgecontr`, fill `ap` | adopted; converter aliases the keys (see RECIPE_SCHEMA.md) |
| 599-byte limit | measured on `JSON.stringify(prepRecipe(...)).length` | `validate()` measures the JSON form, same basis |
| Progress model | `stepCompleted` advances the step; a `dialog` step pauses for the operator and does not auto-advance | coordinator increments on `stepCompleted`, sets *waiting* on `dialog` |
| Events | `is_connected:0/1`, `stepCompleted`, `recipeCompleted`, `dialog:…` | `parse_event` handles each identically |

## Fixed by this audit — a real gap

**A full recipe goes on the wire as XML step-tags, not JSON.** The app hands its
native layer a JSON recipe, but the native layer *parses* it (`getJSONArray` /
`getJSONObject` in the binary) and *builds XML tags* from it (`toUpperCase` on
each type and key), because there are no static step-tag literals in the app —
they are constructed dynamically. So a recipe on the wire is:

```
{msg:1:<START><TMP>205</TMP></START><FR><FWV>250</FWV><RWV>30</RWV><AP>15</AP></FR>…<BO><BT>4</BT></BO>}
```

the same tag form as a manual command, concatenated — **not** the JSON array the
integration was framing. `encode_wire()` now produces the tag form and the brew
path sends it; the JSON form is kept only for the size check, matching how the
app measures the limit. This was the most consequential divergence found: the
manual-command path was always right, but the actual brew was sending JSON a
tag-parsing firmware would likely reject.

## Still unverified — leads, not conclusions

**Dialog response framing.** The app calls `dialogResponse(n)`; the native layer
wraps it. The binary carries a `msg:3:1` literal — a distinct *message type 3* —
which strongly suggests a dialog answer is `{msg:3:<n>}`, not the
`{msg:1:<DIALOG>n</DIALOG>}` the integration currently guesses. Flagged in
docs/PROTOCOL.md; needs a capture to confirm.

**Chunking of a recipe over one BLE write, and what `msg:3` fully means**, remain
open for the same reason — only hardware settles them.

## Deliberately different — a design choice, not a gap

The app's menu/recipe storage is **cloud sync** (`getMenus`, `saveMenu`,
`retrieveMenu`, `deleteMenu`, a hardcoded HTTP endpoint, account login). This
integration replaces all of that with **local storage plus git** — a recipe
library in Home Assistant's own store, exportable to files. Brewing is entirely
local BLE in both; the app's cloud is only for syncing recipes between devices,
and depending on a third-party server for that adds nothing to making coffee.
This divergence is intentional and documented, not an oversight.

## Net

The serialization, framing, schema, size rule and progress model all match the
app. One real behavioural gap — the recipe wire form — is fixed. One guess (the
dialog-response frame) is now a specific lead to confirm on hardware rather than
an open shrug. The cloud path is replaced on purpose.

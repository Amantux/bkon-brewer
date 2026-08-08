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
| `prepRecipe` rules | drop zero-valued size keys; `manstop`→dialog; append `bo` bt=4; URL-encode dialog text; rebuild `start` with a rounded `tmp` | reproduced exactly, including the manstop bug below |
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

## Found in the app source — value ranges, two missing fields, and a bug

Reading the app's step editors (recovered via source maps) surfaced the
validation envelope it enforces before syncing — tighter than the RAIN guide's
typical values, and the authority on what the machine will accept. It corrected
several bounds this project had guessed (temperature 140–212 °F not 165–210;
vacuum setpoint 0–60 kPa not 0–101; **purge pressure 25–35, not 0–100** — the
old default of 50 was invalid; fill/rinse 0–600 ml) and revealed two fields the
step model was missing: a **vacuum** step carries an atmospheric pause `ap`, and
a **purge** step carries a rinse volume `rwv`. Both are now emitted. The full
table is in [INTEL.md](INTEL.md).

**A vendor bug that defines the real wire form.** For a manual-stop purge, the
app means to carry the pressure and time onto the substituted dialog step:

```js
var nobj = {type:'pg', values:{}};
nobj.values.dialog = "Manually stop the purge…";
nobj.values.det = step.values.det + "";
if(!!nobj.values.ps) { nobj.values.ps = step.values.ps + ""; }   // reads nobj, not step
if(nobj.values.tm)   { nobj.values.tm = step.values.tm + ""; }   // always undefined
```

Both guards test the freshly-made empty `nobj`, never the source `step`, so `ps`
and `tm` are **never** copied — the app emits only `{dialog, det}`. That is what
the firmware has always been sent, so `encode()` now drops them too. Matching the
app's *actual output* beats matching its *intent*: fidelity to a real device is
fidelity to its real inputs, bugs included.

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

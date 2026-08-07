# BKON Craft Brewer — protocol notes

Recovered from the BKON Craft Brewer Developer app (v2.0) for the purpose of
talking to a brewer we own. These are notes about the wire format, not a copy of
BKON's software — none of their source is redistributed here.

Everything below is **read off the app, not tested against hardware**. Nothing
has touched a real brewer yet. Sections are marked accordingly, because the
difference matters: a protocol note that looks confident and is wrong is worse
than one that admits it is a guess.

---

## How the app is built (and why that helped)

The Developer APK is a Cordova shell around a Vue/Framework7 web app. Two
consequences:

- The application logic is JavaScript, and the bundle ships **source maps with
  `sourcesContent`** — so the original source, with original file and variable
  names, is recoverable outright. No decompilation involved.
- Only the *transport* lives in `classes.dex`, exposed to the web layer through
  a `window.app.*` bridge. That bridge is the complete API surface of the
  device, and it is small.

## Transport: Nordic UART Service

| UUID | Role |
|---|---|
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | NUS service |
| `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | RX — **write**, host → brewer |
| `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | TX — **notify**, brewer → host |
| `00002902-0000-1000-8000-00805f9b34fb` | CCCD, to enable notifications |

Nordic UART is a byte pipe with no semantics of its own, so everything below is
framing the app itself invented.

**A recipe must serialise to 599 bytes or fewer.** The app refuses to send
anything longer, with "This recipe is too large for Bluetooth LE transmission.
Please consolidate steps". That is a hard constraint on recipe complexity and
belongs in validation, not in a runtime error.

## Framing

Two frames appear as literals in the app:

```
{msg:1:<ABORT></ABORT>}
{msg:1:<CANCEL></CANCEL>}
```

So the shape is `{msg:<n>:<payload>}` with an XML-ish payload. `1` is the only
value seen alongside a payload; a bare `msg:3:1` also appears, unexplained.

**Unverified:** whether `n` is a message type, a sequence number, or a channel;
and how a >20-byte payload is chunked across BLE writes. Both need a capture
from real hardware.

## Commands (host → brewer)

The one complete command literal in the app is a manual purge:

```
<PG><PS>50</PS><TM>10</TM><DET>0</DET><CONTR>0</CONTR></PG>
```

Recipes are handed to the native layer as JSON and converted there. The mapping
is positional and obvious — step `type` and each `values` key become uppercased
tags — which is what makes `pg` + `{ps, tm, det, contr}` produce exactly the
literal above.

```json
[
  {"type": "start",  "values": {"tmp": "205"}},
  {"type": "fr",     "values": {"fwv": "250", "rwv": "0", "dl": "0"}},
  {"type": "vc",     "values": {"ps": "50", "tm": "30"}},
  {"type": "pg",     "values": {"ps": "50", "tm": "10", "det": "0"}},
  {"type": "dialog", "values": {"text": "Add%20grounds"}},
  {"type": "bo",     "values": {"bt": "4"}}
]
```

### Step types

| Code | Name | Notes |
|---|---|---|
| `start` | Start | Heat to temperature. Only carries `tmp`. |
| `fr` | Fill | Fill and rinse volumes, plus a pause. |
| `vc` | Vacuum | The part that makes this machine unusual. |
| `pg` | Purge | Pressure, hold time, delay, detection. |
| `dialog` | Dialog | Pauses and asks the operator something. |
| `bo` | Brew Out | Appended automatically if absent (see below). |

Only **Fill, Vacuum, Purge and Dialog** are offered in the app's own step
picker. `start` and `bo` are structural.

### Value keys

| Key | Meaning | Confidence |
|---|---|---|
| `tmp` | Temperature | Certain — Start editor, rounded to integer |
| `fwv` | Fill water volume | Certain — Fill editor |
| `rwv` | Rinse water volume | Certain — Fill editor |
| `dl` | Delay / pause | Certain — labelled "Pause (<3 mins)" |
| `tm` | Time / hold time | Certain — labelled "Hold Time (<3 mins)" |
| `ps` | Pressure | High — Purge and Vacuum editors |
| `det` | Detection toggle | Medium — boolean in the Purge editor |
| `manstop` | Manual stop | Certain, but **app-side only** — see below |
| `contr` | Unknown | Low — appears only in the purge literal, as `0` |
| `bt` | Brew time | Medium — `bo` step, default `4` |
| `text` | Dialog text | Certain, URL-encoded |

### Serialisation rules the app applies

These are not cosmetic; a re-implementation that skips them will produce
recipes the brewer reads differently.

1. **Zero-valued `fwv`, `rwv`, `ap`, `ps`, `tm`, `dl` keys are deleted, not
   sent as `0`.** Absent and zero mean different things to the firmware.
2. **All values are sent as strings**, including numbers.
3. **`manstop` never reaches the device.** A purge with `manstop=1` is rewritten
   into a purge carrying a `dialog` value — "Manually stop the purge or it will
   close when it's finished" — and the flag is dropped. With `manstop=0` the key
   is simply removed. The firmware has no concept of manual stop; it is the app
   faking one with a dialog.
4. **A `bo` step is appended automatically** with `bt: "4"` if the recipe does
   not already contain one.
5. **Dialog text is URL-encoded**, with `'` additionally escaped to `%27`.
6. **`start` is rebuilt from scratch** keeping only a rounded `tmp`, discarding
   anything else on that step.

## Events (brewer → host)

Pushed up through the bridge as `event:payload` strings:

| Event | Meaning |
|---|---|
| `is_connected:0` / `is_connected:1` | Link state |
| `stepCompleted` | One recipe step finished — drives progress |
| `recipeCompleted` | Brew finished |
| `dialog:<text>` | Brewer is asking something; needs a response |
| `new_device:<…>` | Scan result |
| `notify:<text>` | Human-readable message |

`dialogResponse(<button>)` answers a dialog. `0` is treated as cancel, and the
app closes the brew.

## Errors

`assets/static/error-codes/errors-en.json` is a `module → code → {title, txt}`
table, keyed as `(C:<code> M:<module>)`. Module 2 codes seen include 20
(information missing), 30 (incorrect brew data) and 45 (descale finished).
Worth shipping as a lookup so an integration reports "Descale finished" rather
than "error 45".

## Servings

A recipe carries **three portions** — the app's editors are laid out as
serving 1 / 2 / 3, each with independent fill, rinse and pause values. Brewing
selects one portion and sends only its step list.

## The cloud is not required

The app talks to `http://52.42.41.9/bkon/api/` (hardcoded IP, plain HTTP) for
account login and recipe storage. That is **menu synchronisation only** —
brewing is entirely local over BLE. An integration can ignore it completely,
which is the right call: it is a third-party dependency, unencrypted, and
contributes nothing to actually making coffee.

---

## What still needs hardware to confirm

1. Chunking of payloads longer than one BLE write.
2. What `{msg:N:…}` numbering means.
3. What `contr` does — it is `0` in the only example.
4. Whether the brewer emits anything unsolicited (temperature, progress) beyond
   the step/recipe completion events.
5. Units and legal ranges for `ps`, `fwv`, `rwv` — the app constrains inputs to
   3 characters and validates times under 3 minutes, but the units are not
   stated anywhere in the source.

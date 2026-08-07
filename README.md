# BKON Craft Brewer — Home Assistant integration

Control a BKON Craft Brewer from Home Assistant over Bluetooth, and build
recipes without the vendor app or its cloud account.

**Status: built, not yet hardware-tested.** The protocol was recovered from the
vendor's own app; the pure layers (recipe encoding, event parsing, message
framing) are covered by 65 assertions, but nothing has spoken to a real brewer
yet. Every unconfirmed decision is labelled as such, here and in the code.

```
./tests/run_all.sh          # 65 assertions, no dependencies
```

---

## What it does

- **Brew a recipe** from a list of steps — the `bkon_brewer.brew` service.
- **Manual purge**, **abort**, **answer a dialog** — as services and, for the
  common ones, one-tap buttons.
- **See what the brewer is doing** — status, current step, outstanding operator
  prompt, and last error as sensors, updated the instant a notification arrives
  (`local_push`, not polled).
- **No cloud, no login.** The vendor app gates its recipe *library* behind an
  account, but brewing itself is entirely local over Bluetooth. This integration
  never touches BKON's servers.

## How it reaches the brewer

The brewer speaks **Nordic UART** (a generic BLE serial service). Home Assistant
routes to it through whatever connectable adapter is in range — on a setup with
no host radio, that means an **ESPHome Bluetooth proxy**. That is transparent to
the integration: it asks Home Assistant for the device by address and gets a
connection, wherever the radio physically is.

Practical consequence: **the brewer must be within BLE range of a proxy**, and
ESP32 proxies hold only a few connections at once. If several BLE devices share
one proxy, a dedicated proxy near the brewer is the reliable answer.

## Recipe model

A recipe is a list of steps. Five types matter:

| Type | Code | What it does |
|---|---|---|
| Start | `start` | Heat to a temperature |
| Fill | `fr` | Fill and rinse volumes, plus a pause |
| Vacuum | `vc` | The vacuum extraction this machine is built around |
| Purge | `pg` | Pressure, hold time, detection |
| Dialog | `dialog` | Pause and ask the operator something |

A brew-out is appended automatically. Example service call:

```yaml
service: bkon_brewer.brew
data:
  steps:
    - {type: start,  values: {tmp: 205}}
    - {type: fr,     values: {fwv: 250, rwv: 30}}
    - {type: vc,     values: {ps: 50, tm: 30}}
    - {type: pg,     values: {ps: 50, tm: 10, det: 1}}
    - {type: dialog, values: {text: "Add grounds"}}
```

The encoder faithfully reproduces the vendor app's serialisation, **including
the parts that look like bugs**, because deviating would mean identical inputs
brewing differently through this path than through the app — and the only
symptom is disappointing coffee. Those rules, and why each one matters, are in
[docs/PROTOCOL.md](docs/PROTOCOL.md). The short version:

- Zero-valued size fields are dropped, not sent as `0` (absent ≠ zero).
- `manstop` never reaches the device — the app fakes manual-stop with a dialog.
- Dialog text is URL-encoded, apostrophes included.
- Recipes must fit **599 bytes**, enforced at build time with a message that
  says what to trim.

## What still needs a real brewer

Listed in full in [docs/PROTOCOL.md](docs/PROTOCOL.md). The load-bearing ones:

1. **Chunking of payloads over one BLE write** — the reassembly is implemented
   and the split logic is tested, but the brewer's side is unconfirmed.
2. **The dialog-response wire format** — the app calls a native method whose
   payload we have not captured.
3. **Units and ranges** for pressure and volumes.

The `bkon_brewer.send_raw` service exists for exactly this: send a hand-framed
string and watch what comes back, to nail these down against hardware.

## Layout

```
custom_components/bkon_brewer/
  protocol/
    recipe.py     recipe model + wire encoding   (pure, tested)
    events.py     brewer -> host event parsing    (pure, tested)
  transport.py    Nordic UART over HA Bluetooth   (thin; framing split tested)
  coordinator.py  connection lifecycle + brew state
  config_flow.py  Bluetooth discovery + manual entry
  sensor.py       status / step / dialog / error
  button.py       abort, manual purge
docs/PROTOCOL.md  the recovered protocol, with per-field confidence
tests/            65 assertions, no dependencies
```

Parsing is pure and tested; I/O is thin and clearly marked unverified. None of
the vendor's application code is in this repository — documenting a protocol to
interoperate with hardware you own is not the same as redistributing their app.

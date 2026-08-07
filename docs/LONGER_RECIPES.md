# Longer recipes: the file path vs the 599-byte Bluetooth limit

## The question

A recipe brewed over Bluetooth is capped at 599 bytes — the app refuses to
transmit anything larger, calling it "too large for Bluetooth LE transmission".
Can loading a recipe as a *file* onto the machine escape that cap?

## The answer: yes

The 599-byte limit is a **Bluetooth transmission** limit, not a limit on what a
recipe can be. The machine holds an on-board menu, and BKON/Franke's own service
documentation describes loading it from a file over USB, entirely separate from
Bluetooth:

- The machine's **Service Menu → "Update Recipe File"** loads a menu/recipe file
  from a USB drive onto the unit.
- **"Export to Recipe File"** copies the unit's current menu back out to USB.
- Software and config updates use the same USB path (a thumb drive into the
  machine).

None of these touch Bluetooth, so none are bound by the 599-byte BLE write. A
recipe with many steps — more vacuums, more dialogs — that would never fit
through a BLE brew can be loaded this way and lives in the machine's on-board
menu, brewed from the unit rather than pushed each time from a phone.

So there are two ways a recipe reaches the machine, with very different limits:

| Path | Transport | Size limit |
|---|---|---|
| Brew now | Bluetooth (`sendRecipe`) | **599 bytes** |
| Menu file | USB "Update Recipe File" | none observed |

## What the integration can and cannot do about it

**Cannot:** push a USB file. This integration reaches the machine only over
Bluetooth (through an ESPHome proxy), and the USB path needs a thumb drive
physically inserted into the machine. That is a human step, at the unit.

**Can:** produce the file. The `bkon_brewer.export_menu` service writes all
recipes as one menu object in the machine's own format, with every portion,
downloadable at `/local/bkon/<file>`. You copy it to a thumb drive and load it
through the Service Menu. Because it is a file, the recipes in it are not held to
the BLE 599-byte cap.

The `lint_recipe` check still reports the 599-byte size, because that is the
limit for *brewing over Bluetooth*. A recipe that exceeds it is not broken — it
simply has to reach the machine as a menu file rather than a BLE brew, and the
lint note should be read that way.

## What is confirmed vs. inferred

**Confirmed** from the service docs: the USB "Update Recipe File" / "Export to
Recipe File" path exists, is separate from Bluetooth, and is how larger or
bulk menu changes are made.

**Not fully confirmed:** the exact on-USB *folder layout* the Service Menu
expects. The software-download instructions show a specific folder structure on
the drive (a named sub-folder, particular files), so a menu file may need to sit
in a prescribed place, not just be any JSON. `export_menu` produces the recipe
and menu OBJECT in the app's shape — the payload — but the surrounding layout
should be checked against an actual "Export to Recipe File" dump from the unit
before relying on it. That export is the cleanest way to capture the real format,
and the machine can produce one itself.

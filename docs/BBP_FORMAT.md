# The `.bbp` menu file

The machine's on-board menu is a **`.bbp`** file, loaded over USB. This is what
BKON's Craft Cloud produces from its *Compile* button, and it is the route to
recipes larger than a Bluetooth brew allows (see
[LONGER_RECIPES.md](LONGER_RECIPES.md)).

The format was recovered from **three real files** shipped inside a vendor
software-update package: a beverage menu, a copy of it installed as the menu
resource, and a service menu. Every claim below is verified against all three.

> **The container is understood; the framing is partly inferred.** The record
> encoding, the tag vocabulary and the checksum are confirmed byte-for-byte. The
> exact widths of a few header and category fields are still being pinned down —
> see [What is not confirmed](#what-is-not-confirmed). **Do not flash a
> hand-built file to a machine you cannot recover** (see [Risk](#risk)).

## The container

```
offset  size  meaning
0       4     magic: "BKON" (beverage menu) or "BKOn" (service menu)
4       4     u32le, always 12 — header length or version
8       …     body (see below)
end-4   4     u32le checksum over every preceding byte
```

The body ends with a `<COMMAND>…</COMMAND>` block in all three files.

### The checksum — confirmed

The trailing four bytes are **JAMCRC**: CRC-32 with the final XOR omitted, i.e.
the bitwise complement of the ordinary CRC-32, stored little-endian, computed
over the whole file except the trailer itself.

```python
import struct, zlib
trailer = struct.pack("<I", zlib.crc32(body) ^ 0xFFFFFFFF)
```

Verified against all three files:

| File | Trailer | `~crc32(body)` |
|---|---|---|
| `Ser82018.BBP` | `0x995edc9b` | `0x995edc9b` |
| `FrkMenu.BBP` | `0x1a6bbd46` | `0x1a6bbd46` |
| `MENU.FBP` | `0xe907b6a7` | `0xe907b6a7` |

## Steps — confirmed

This is the part that matters most, and it is unambiguous. A step is:

```
u32le  step type
u8     length of the tag string
bytes  the tag string, ASCII
```

3 461 step records parse cleanly across the three sample files, and every
one re-encodes to the exact bytes it was read from.

| Type | Step | Tags seen |
|---|---|---|
| `0` | Start / heat | `<TMP>` (and a `<DESCALE>` / `<DV>` variant) |
| `1` | Fill | `<FWV>` `<RWV>` `<AP>` |
| `2` | Vacuum | `<PS>` `<TM>` `<AP>` |
| `3` | Purge | `<PS>` `<TM>` `<DET>` `<CONTR>` |
| `4` | Brew out | `<BT>` |

A real portion, decoded:

```
[0] <TMP>170</TMP>
[1] <FWV>300</FWV>
[2] <PS>28</PS><TM>7</TM>
[1] <FWV>25</FWV><RWV>25</RWV><AP>20</AP>
[3] <PS>30</PS><TM>20</TM><DET>1</DET><CONTR>1</CONTR>
[1] <RWV>70</RWV>
[4] <BT>4</BT>
```

Portions open with a type-0 and close with a type-4 — the service menu balances
exactly, 111 of each. That is the same "a brew-out is appended for you" rule this
project already implements.

### What this settled about our own encoder

Three decisions in [protocol/recipe.py](../custom_components/bkon_brewer/protocol/recipe.py)
were inferred from the vendor app and are now confirmed against real device files:

- **Tags, not JSON, and uppercase** — the wire form is XML-ish tags.
- **`AP` is the fill pause**, not `DL`. This project had it as `dl` and corrected
  it earlier from app data; the device files confirm `AP`.
- **`DET` and `CONTR` are the purge flags** on the wire, spelled out in full.

## Strings and structure

Strings are length-prefixed. Category names use a two-byte length; recipe names,
recipe codes and portion names use a single byte.

```
category := name, 4-byte colour (RGB + pad), recipe count, recipes…
recipe   := name, code, portion count, portions…
portion  := name ("small" / "medium" / "large"), step count (u16be), steps…
```

Recipe names may contain a newline — the machine renders a two-line button, e.g.
`"Sencha \nDLT"`. The *code* field carries the dial-in name from the menu
development guide, e.g. `"170/0/10 FGT"`. Unused buttons are real records named
`"Empty"` with zero portions, so a menu is a fixed grid, not a sparse list.

## Two kinds of file

**`BKON`** — a beverage menu. Opens with machine parameters as plain tags
(`<ASF>25</ASF>`, `<TBH>125</TBH>`, `<CTRF>5</CTRF>`, `<KPVAL>14</KPVAL>`,
`<KDVAL>16</KDVAL>`, `<KPNEG>…`) before the categories. `MENU.FBP` is the same
file under the name the installer flashes.

**`BKOn`** (lowercase `n`) — a service menu. Same record format, but its
"recipes" are diagnostic routines: *Neg Pressure Leak Test*, *Tower*, *WVSC*.

## How a file reaches the machine

The update package carries an `INSTALL.INI` that names the target explicitly:

```ini
[Menu]
name=Menu Resource
file=0:TeaBrew/MENU.FBP
image=false
type=flash
device=Flash0
address=0x80000000
```

So the layout on the USB stick is load-bearing: a `TeaBrew/` folder containing
`INSTALL.INI` and the menu file, with a second `INSTALL.INI` at the root
pointing to it. The user interface is a third-party product ("TeaBrewer", by
M‑Wave Controls), which is why the file format looks nothing like the app's
Bluetooth protocol.

The menu-development guide adds one more constraint: a compiled menu's
**filename must be no more than eight characters**. The real files obey it —
`FrkMenu`, `Ser82018`, `MENU`.

## What is not confirmed

- **Header bytes 8–15.** A five-field guess parses the first category correctly
  but drifts later in the file, so the category-table framing is not yet exact.
  The step records are unaffected — they are self-describing.
- **The category count and per-category recipe count widths.**
- **Whether the machine validates anything beyond the checksum** (a length field,
  a version, a signature).
- **`<DESCALE>` / `<DV>`** on a start step (a descale routine's variant).
- **One unmatched brew-out in the beverage menus.** Portions pair a start with a
  brew-out; the service menu balances exactly (111/111) but both beverage menus
  come out 123/124. Either a portion legitimately has no start step, or the
  scanner misses one. Small, but unexplained, so it is written down rather than
  rounded off.

## Risk

`INSTALL.INI` flashes the menu to `Flash0` at `0x80000000` on the user-interface
board. A malformed file is written to the same place a good one is. Until the
framing above is exact and a round-trip has been verified against a file the
machine itself exported, **treat writing a `.bbp` as unfinished work, not a
feature**. The safe next step is the machine's own *Service Menu → Export to
Recipe File*: it produces a known-good file from your unit, which would confirm
the framing and give a byte-for-byte target to reproduce.

## Provenance

Recovered from a vendor software package in the owner's own archive, for
interoperability with hardware they own. No vendor file is redistributed here —
this document describes a format, which is a fact about it, not its contents.

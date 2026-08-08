# Intel from the service documentation

Facts folded in from an archive of BKON's (now Franke's) service and training
portal — 53 documents the owner archived for their own machine. This file
records what those documents *established* for the protocol, not their contents:
units, ranges and error meanings are facts, and facts are what an integration
needs. None of the source documents are reproduced here or in the repository.

## What it confirmed

**The vendor is Franke.** The service PDFs carry Franke's copyright; BKON's
brewer line is theirs. Nothing changes for the integration except attribution.

**Units — previously guessed, now settled.** The RAIN Menu Development Guide
states them outright, which retired the largest open question in
[PROTOCOL.md](PROTOCOL.md):

| Field | Unit | Typical operating values |
|---|---|---|
| Temperature (`tmp`) | °F, delivered to ±1 °F | ~165–205 °F across the documented tea menus |
| Fill / rinse (`fwv` / `rwv`) | millilitres | fills ~35–250 ml |
| Vacuum strength (`ps` on `vc`) | kilopascals | base recipes ~20–24 kPa |
| Steep / pause / hold (`tm` / `dl`) | seconds | a few seconds to ~15 s |

**The vacuum is the whole point.** The guide frames temperature and time as
ordinary brewing variables and the *vacuum* as the machine's distinguishing
mechanism — extraction under reduced pressure, held for only seconds. That is
why the builder colour-codes the vacuum step distinctly and the model treats
`vc` as first-class rather than a variant of purge.

**A useful base-recipe relationship.** The guide describes how the vacuums in a
sequence relate: if the first vacuum is X kPa, the next is around X+2 and the
one after around X+1, with steep times tuned per menu. This is reference
material for anyone designing recipes, not something the protocol enforces — but
it tells you the sensible neighbourhood for a value, which a bare min/max cannot.

**The dial-in convention — which validated the advisor after the fact.** Recipes
are named `temp/vacuum/steep` (`185/0/0` is a category mid-point). The guide's
rule: move the **vacuum in big steps of ±2 kPa** to change *concentration*, and
the **steep in small steps of ±5 or ±10 s** at the end of the recipe to change
*flavour intensity*. [advisor.py](../custom_components/bkon_brewer/advisor.py)
was written to move vacuum by 2 and steep by 5 per request — reasoned guesses
that turn out to match the documented convention exactly.

**Base recipe starting points.** The low-temperature tea menu starts at
175 °F / 24 kPa, the high-temperature menu at 205 °F / 20 kPa — a hotter brew
starts from a *shallower* vacuum. Delicate-leaf teas use one vacuum, a much
shorter steep, and front-loaded water, because repeated vacuums over-extract
them. That is the shape the `delicate` template already had.

**The menu file is a compiled `.bbp`, and menus have a fixed capacity.** Menus
are authored in BKON's Craft Cloud; a **Compile** step emits a `.bbp` whose
filename must be **≤ 8 characters**, and that is what the USB path ingests — not
arbitrary JSON. A menu holds 8 categories × 4 pages × 8 buttons = **32 recipes
per category, 256 per menu**. This *narrowed* what `export_menu` can claim; see
[LONGER_RECIPES.md](LONGER_RECIPES.md).

**The error table.** The Error Codes reference gave clean hardware-fault labels
(chamber-not-sealed, flow-meter, LIM-communication, the temperature-sensor
bank) that the app's JSON table stated only in longer support prose. Both agree
on the `(C:code M:module)` keys; the integration now ships the concise labels.

## What it did *not* change

The BLE protocol itself is unchanged — the service docs are about installing,
operating and repairing the machine, not talking to it over Bluetooth. Menu and
software updates in the documentation go over **USB and on-screen service
menus**, a separate path from the app's BLE link. So the open items in
[PROTOCOL.md](PROTOCOL.md) that need a live capture — chunking, the `{msg:N}`
numbering, the dialog-response frame — are untouched by this and still need
hardware.

## Provenance

The archive lives at `Amantux/bkon-archive` (the owner's private mirror). It is
referenced, never vendored: this integration depends on none of it at runtime,
and the facts above would be equally true read from a machine's own display.

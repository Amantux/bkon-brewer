# Recipe schema

The recipe format, matched to what the BKON app itself produces. Recovered from
the app's own menu data; this documents the *shape*, not the app's recipes.

## The app's recipe object

A recipe as the app stores it is a nested object, not a flat list of steps:

```
recipe:
  id, name, dsp_name, description, notes, status, code, image, date, modified
  sequences:
    portions:                       # serving sizes — the app uses three
      - name: small
        sequences: [ step, ... ]
      - name: medium
        sequences: [ step, ... ]
      - name: large
        sequences: [ step, ... ]

step: { type, values }
```

Recipes live inside a menu → category hierarchy in the app's cloud
(`menu: {id, description, recipes:[category]}`,
`category: {color, name, recipes:[recipe]}`), but a single recipe object is the
unit this integration reads and writes. The default recipe files in
`custom_components/bkon_brewer/defaults/` and the export/import files are in this
shape, so a file matches what the app produces.

## Step types and value keys

| Step | `type` | Value keys |
|---|---|---|
| Start | `start` | `tmp` |
| Fill | `fr` | `fwv`, `rwv`, `ap` |
| Vacuum | `vc` | `ps`, `tm`, `ap` |
| Purge | `pg` | `ps`, `tm`, `dl`, `purgedet`, `purgecontr` |
| Dialog | `dialog` | `text` |
| Brew out | `bo` | `bt` |

Two key facts the app data settled, both of which a naive model gets wrong:

**A fill's pause is `ap`, not `dl`.** `ap` is the *atmospheric pause* — the
steep at normal pressure, in seconds — and it lives on Fill and Vacuum steps.
`dl` is the *purge delay*, a different key on a different step. Storing a fill's
pause as `dl` puts it where the firmware does not read it, and the steep
silently does nothing.

**A purge's flags are `purgedet` / `purgecontr` in the stored recipe, but `det`
/ `contr` on the wire.** The menu format and the BLE form differ by exactly these
two keys. `app_recipe.py` aliases them on conversion, so a purge keeps its flags
crossing between the stored file and the encoder.

## Two forms, one converter

- **Stored / files / defaults** — the app's nested object above, with `purgedet`
  keys. This is the git-committable, app-compatible form.
- **Internal** — one portion's flat `[{type, values}]` in wire keys (`det`),
  which is what the BLE encoder sends.

`app_recipe.from_app_recipe(obj, portion=None)` yields `(name, flat steps)` for a
chosen portion (the first by default); `to_app_recipe(name, portions, …)` builds
the object back. The library holds the flat form of a recipe's default portion;
exports wrap it as a single-portion app object. Hand-authored defaults may carry
several portions, and seeding takes the first.

## The bundled defaults

Grounded in BKON/Franke's RAIN Menu Development Guide (see `docs/INTEL.md`), not
in taste — a defensible place to start, tuned from there with the advisor:

| Recipe | Basis |
|---|---|
| Classic Pour Over | The guide's worked base recipe: 241 ml fill, a 24 kPa vacuum held four seconds, a short steep. |
| Low-Temperature Tea | Tea base at 175 °F, vacuum ladder 24 → 26 → 25 kPa (the guide's X, X+2, X+1). |
| High-Temperature Tea | Tea base at 205 °F, shallower ladder 20 → 22 → 21 kPa. |
| Medium Roast Coffee | One weak vacuum held four seconds at the zero-point, per the coffee base. |

Each ships with three portions (small / medium / large) scaled by fill volume.

## Serving sizes

The scaling is exact and worth stating: **medium ±25% of the fill volume, and
nothing else**. Classic Pour Over is 181/241/301 ml, both tea menus are
188/250/312. Temperature, vacuum depth and steep times are identical across the
three — which follows from the documented dial-in convention, since vacuum sets
concentration and steep sets intensity, so moving them between sizes would serve
a different drink rather than more of the same one.

This integration carries all three end to end. `R.sizes_from()` derives them
from whichever size you built, through a notional medium rather than
size-to-size (scaling small straight to large chains two roundings and gives 302
where the vendor says 301). `save_recipe` takes a `sizes` map and validates each
separately; `brew_saved` takes a `size` and **refuses one the recipe does not
have** rather than substituting the default, because the failure there is
handing someone a different drink.

Before this, `library.py` took the first portion and dropped the rest, so every
recipe the vendor ships arrived as a single size.

## Unverified

`purgecontr` (purge control) appears in every stored purge as `1`, but its
effect is not documented anywhere in the recovered material. The integration
carries it through faithfully rather than guessing at it. See `docs/PROTOCOL.md`
for the other items still awaiting a hardware capture.

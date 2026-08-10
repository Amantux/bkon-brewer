# Mobile & accessibility audit — `addon/webroot/index.html`

> **Status: a point-in-time audit, partly acted on.** Taken August 2026 against
> a much earlier build. Several findings have since been fixed and several
> sections describe markup that no longer exists, so check anything here against
> the current file before acting on it.

Read-only audit of the add-on's single-file UI as it renders inside Home Assistant's
ingress iframe. This was a **static** audit — nothing was rendered; items that
genuinely need a browser are listed at the end under
[Not determinable without rendering](#not-determinable-without-rendering).

> **Basis and drift.** Line numbers refer to a snapshot of `addon/webroot/index.html`
> taken at the start of this audit (2697 lines). The file was being refactored
> concurrently — a design-token pass introducing `--fs-*` and `--r-*` variables — and had
> already diverged by ~570 lines when the audit finished. **Every finding below was
> re-verified against the live file and all of them still apply**, but line numbers have
> shifted by roughly −25 to −55 in the CSS and JS. Live positions for the five Broken
> items at time of writing: B1 → 1321, B2 → 1606–1609, B3 → 494–497 & 501–513,
> B4 → 2586/2665, B5 → 2097 & 2129.
>
> One item got *worse* in the refactor: `.br-bar input/select` and `.setrow input/select`
> moved from a literal `14px` to `var(--fs-lg)` = **13.5px** (live lines 315, 416), and
> `.stu-input input` to `var(--fs-md)` = **12.5px** (live line 246). The new
> `--fs-xl:16px` token exists and its own comment names it as the iOS no-zoom size — these
> three rules just do not use it. See **P1**.

## Summary

| # | Severity | Area | Finding | Line |
|---|---|---|---|---|
| B1 | Broken | Companion | `show()` strips `.on` from `#cmp` while the FAB is still `display:none` — the assistant is unreachable until reload | 1351, 2664 |
| B2 | Broken | Toast | Faded-out toast keeps `pointer-events` — an invisible pill permanently eats taps at bottom-centre | 1632–1641 |
| B3 | Broken | Nav / a11y | All 17 primary + wiki nav items are `<a>` with **no `href`** — not focusable, not exposed as links, no pointer cursor | 545–548, 552–564 |
| B4 | Broken | iOS | Companion `focus()`es its input on open while the panel is `position:fixed; bottom:16px` — the soft keyboard covers the composer | 487–488, 2665 |
| B5 | Broken | Ingress | "Copy call" silently does **nothing** in an insecure context (`http://` HA) — optional chaining swallows the whole chain including `.catch` | 2097–2099, 2128 |
| P1 | Poor | iOS zoom | `.br-bar input/select`, `.stu-input input` (Ask + Compose) at 13–14px; `.setrow` fixed only ≤600px | 235, 304, 405, 478 |
| P2 | Poor | Overflow | `.dg-cite .doc`, `.md code`, `.dg-page p`, wiki `<table>` can exceed the viewport; `main`/`.layout` lack `min-width:0` | 28, 44, 358, 374, 401 |
| P3 | Poor | Overlays | No background scroll lock, no focus trap/return, no `role="dialog"` on drawer, reader or companion | 1379–1383, 2506, 2659 |
| P4 | Poor | Contrast | `--ink-faint` fails 4.5:1 in **both** themes (2.62–3.50); white-on-`--accent` is **2.93:1 in dark** | 9–24 |
| P5 | Poor | Layout | `.br-grid` forces 2 columns at 360–390px; the 3 card buttons end up ~41px wide | 331 |
| P6 | Poor | Layout | `.stu-head` is a no-wrap flex row with 4 controls — badge/name/description are crushed at 360px | 143 |
| P7 | Poor | Targets | `.dg-watch` (an `<a>`) misses the coarse `min-height` its sibling `<button>` gets; `.stu-describe>summary` ~28px; `.stu-chipcard .del` ~17px wide; `.stu-tog` ~23px | 163, 296, 376, 525 |
| P8 | Poor | a11y | Step-field `<label>`s are siblings of their inputs with no `for` — every number field in the builder is unnamed | 1487–1497 |
| P9 | Poor | Drawer | `.topbar` (z 30) paints over the open drawer (z 25), hiding the brand block | 173, 182 |
| P10 | Poor | Ingress | `.bbp` export calls `window.open()` **after** an `await` — outside the user-activation window | 2119 |
| P11 | Poor | Studio | Drag-to-reorder has no edge auto-scroll and `touch-action:none` blocks panning — long recipes can't be reordered by drag on a phone | 107–108, 1546 |
| L1 | Polish | CSS | ~70 lines duplicated verbatim inside `@media (max-width:600px)` | 408–478 |
| L2 | Polish | a11y | `role="radiogroup"` over `<button>` children, no `aria-checked`; zero `aria-live` anywhere in the file | 896 |
| L3 | Polish | Theme | No `<meta name="color-scheme">` — UA widgets and scrollbars stay light in dark mode | 4–6 |
| L4 | Polish | Motion | `prefers-reduced-motion` misses the drawer slide and the gauge/score bar width transitions | 183, 245, 262 |
| L5 | Polish | Focus | `outline:none` on 6 input rules with no `:focus-visible` replacement — there is **no** `:focus-visible` rule in the file | 162, 237, 249, 279, 407, 504 |
| L6 | Polish | Layout | `main{max-width:820px}` in a `1fr` track leaves ~390px dead space at 1440px | 44 |
| L7 | Polish | Targets | `.stu-ic` computes to 40×42 on touch, `.stu-star` ~28–35px wide — short of 44 | 190, 205–207 |
| L8 | Polish | Collision | The toast (`bottom:20px`, centred) overlaps the FAB at 360px | 1636, 198 |

---

# Broken

### B1 — Navigating away kills the companion permanently

`show()` (line 1350) collects **every** `<section>` in the document, not just the pages:

```js
const secs=document.querySelectorAll('section');
...
secs.forEach(s=>s.classList.toggle('on', s.id===id));
```

The floating companion is `<section class="cmp" id="cmp">` (line 1335) and `.cmp.on{display:flex}`
is what makes it visible (line 490). Meanwhile `open()` hides the launcher with an inline style:

```js
function open(){ panel.classList.add("on"); ... fab.style.display="none"; ... }   // 2659-2666
function close(){ ... fab.style.display=""; }                                     // 2669
```

So: open the assistant → tap any nav link → `show()` removes `.on` from `#cmp`, the panel
vanishes, but `close()` never runs, so the FAB stays `display:none` and `aria-expanded`
stays `"true"`. **The assistant cannot be reopened without a page reload.** On a phone,
where switching pages is the normal thing to do, this fires almost immediately.

Fix — scope the page switch to real pages and let the companion opt out:

```js
const secs = document.querySelectorAll('main > section');
```

`main > section` is already the selector the CSS uses (line 48), so this makes JS and CSS
agree. Nested `.zone` sections and `#cmp` then stop being touched at all.

### B2 — The toast permanently blocks taps once it has fired

```js
t.style.cssText="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);"
  +"...;z-index:60;opacity:0;transition:opacity .18s";      // 1635-1637
...
clearTimeout(flashTimer); flashTimer=setTimeout(()=>{t.style.opacity="0";},1500);  // 1640
```

Hiding is done with `opacity:0` only. The element stays in the layout, `position:fixed`,
`z-index:60`, roughly 200×38px, dead centre at the bottom of the viewport — and it still
receives pointer events. After the first "Copied save_recipe call", every subsequent tap in
that band is swallowed. On a 360px phone that band sits directly over the bottom of the
content area and over part of the FAB.

Fix — add `pointer-events:none` to the inline `cssText` (it never needs to be clickable):

```js
+"border-radius:99px;box-shadow:var(--shadow);z-index:60;opacity:0;"
+"pointer-events:none;transition:opacity .18s"
```

### B3 — The entire navigation is keyboard- and screen-reader-invisible

```html
<a data-nav="studio" class="active primary">🧪 Recipe studio</a>   <!-- 545 -->
<a data-nav="browse" class="primary">📖 Recipes</a>                <!-- 546 -->
...
<a data-nav="overview">Overview</a>                                <!-- 552 -->
```

None of the 4 primary links or the 13 wiki links carry an `href`. An `<a>` without `href`
is not in the tab order, is not exposed with the `link` role, does not respond to Enter, and
does not get `cursor:pointer`. There is no other route to any page. Note the *inline* links
in prose (lines 607, 714, 743, 919) **do** have `href="#"` — the omission is only in the nav.

Fix — give each one a real fragment; the existing delegated handler already calls
`e.preventDefault()` (line 1359), so nothing else changes:

```html
<a data-nav="studio" href="#studio" class="active primary">🧪 Recipe studio</a>
```

Add `nav.side a{cursor:pointer}` for good measure, and mark the current page with
`aria-current="page"` in `show()` alongside the existing `active` class toggle.

### B4 — iOS: the companion composer ends up behind the keyboard

```css
.cmp{position:fixed;right:16px;bottom:66px;...;max-height:min(560px,calc(100vh - 96px))}  /* 487 */
@media (max-width:800px){ .cmp{bottom:16px;max-height:min(70vh,560px)} }                   /* 199 */
```
```js
function open(){ ...; $("cmpInput").focus(); }   // 2665
```

Opening the panel focuses the input, which raises the soft keyboard. On iOS Safari/WKWebView
`position:fixed` resolves against the **layout** viewport, which the keyboard does not shrink,
so the panel's bottom edge — the `.cmp-form` with the text field and Send — stays underneath
the keyboard. The user is typing into something they cannot see. The HA companion app on iOS
is a WKWebView, so this is the default experience, not an edge case.

Fix — anchor to the visual viewport where supported and drop the autofocus on touch:

```css
@supports (height: 100dvh) {
  @media (max-width:800px){ .cmp{max-height:min(70dvh,560px)} }
}
```
```js
if (!matchMedia('(pointer:coarse)').matches) $("cmpInput").focus();
```

and, for iOS specifically, reposition on `visualViewport` resize:

```js
addEventListener('resize', () => {
  const vv = window.visualViewport; if (!vv) return;
  panel.style.bottom = Math.max(16, innerHeight - vv.height - vv.offsetTop + 16) + 'px';
}, {passive:true});
```

### B5 — "Copy call" does nothing at all over plain HTTP

```js
$("stuCopy").onclick = () => {
  navigator.clipboard?.writeText(yaml())
    .then(()=>flash("Copied save_recipe call")).catch(()=>flash("Copy blocked — select manually"));
};                                                                    // 2097-2099
```

Optional chaining short-circuits the **whole** member chain. When `navigator.clipboard` is
`undefined` — which is the case for any non-secure context, i.e. Home Assistant reached at
`http://homeassistant.local:8123` or `http://192.168.x.x:8123`, by far the most common setup —
the entire expression evaluates to `undefined`. No copy, no `.catch`, no toast, no console
error. The button is inert and gives zero feedback. The same pattern is at line 2128 for
"Send to brewer" when HA is not connected.

Worse, the intended failure message ("select manually") is unactionable: the YAML is never
rendered anywhere the user could select it.

Fix — branch explicitly and fall back to something selectable:

```js
async function copyOut(text, ok){
  try {
    if (!navigator.clipboard) throw new Error('no clipboard');
    await navigator.clipboard.writeText(text);
    flash(ok);
  } catch {
    showYamlDialog(text);            // a <dialog> with a readonly <textarea> the user can select
  }
}
$("stuCopy").onclick = () => copyOut(yaml(), "Copied save_recipe call");
```

---

# Poor

### P1 — iOS zooms the page on four of the most-used inputs

Safari zooms on focus whenever the field's font-size is below 16px. The `@media (max-width:800px)`
block (lines 186–193) correctly lifts `.stu-f input`, `.stu-name`, `.stu-notes` and
`.cmp-form input` to 16px. It misses:

| Control | Rule | Size | Line |
|---|---|---|---|
| `#askText` (Diagnose), `#nlText` (Compose) | `.stu-input input` | **13px** | 235 |
| `#brSearch`, `#brSort` | `.br-bar input,.br-bar select` | **14px** | 304 |
| `#setUrl`, `#setKey`, `#setModel`, `#setProvider`, `#setModelPick` | `.setrow input,.setrow select` | 14px, raised to 16px **only ≤600px** | 405 / 478 |

`#askText` is the single most-used control on the Diagnose page and it zooms every time.
The Settings gap bites at 601–800px, which is exactly iPad portrait (768px) — and 768px is
already in drawer mode, so it is unambiguously "mobile" by the file's own definition.

Fix — inside the existing `@media (max-width:800px)` block (near line 193):

```css
.stu-input input, .br-bar input, .br-bar select,
.setrow input, .setrow select { font-size:16px }
```

and change the Settings override at line 478 from `@media (max-width:600px)` to sit in the
800px block, keeping only the `grid-template-columns:1fr` change at 600px.

**Post-refactor note.** The concurrent token pass moved these three rules onto `var(--fs-lg)`
(13.5px) and `var(--fs-md)` (12.5px), i.e. *further* from 16px, while introducing
`--fs-xl:16px` whose own comment reads: "it is the size mobile Safari stops zooming a focused
input at, so form fields on touch land on a real token." The token is right; these rules do
not use it. The cleanest fix is now:

```css
@media (max-width:800px){
  .stu-input input, .br-bar input, .br-bar select,
  .setrow input, .setrow select { font-size:var(--fs-xl) }
}
```

### P2 — Horizontal overflow: four real sources, and no structural guard

`main` is a grid item (`.layout{display:grid;grid-template-columns:230px 1fr}`, line 28; `1fr`
at ≤800px, line 181). A grid item's automatic minimum size is its **min-content** width, so
anything inside `main` that cannot shrink widens the track and scrolls the whole body sideways.
Neither `.layout` nor `main` sets `min-width:0`.

**Handled correctly** (worth saying so): `.md-tablewrap{overflow-x:auto}` wrapping
`.md-table{min-width:420px}` (lines 361–362) is exactly the right pattern for the Diagnose
answer tables, and `pre{overflow-x:auto}` (line 61) contains the ASCII architecture diagram at
line 1011. `.br-bar input{flex:1 1 200px;min-width:0}` with `flex-wrap` (lines 303–306) is also
correct.

The actual leaks:

1. **`.dg-cite .doc`** (line 374) — `flex:1;min-width:0` lets it *shrink* but text still will not
   *break*. Source document names arrive from the retriever and are typically underscore- or
   hyphen-joined with no spaces (`BKON_Craft_Brewer_Service_Manual_Rev_C.pdf`), giving a
   min-content width well over 328px.
   Fix: `.dg-cite .doc{overflow-wrap:anywhere}`.
2. **`.md code`** (line 358) — model-authored inline code (paths, URLs, base64) has no break rule.
   Fix: `.md code{overflow-wrap:anywhere}`.
3. **`.dg-page p`** (line 401) — `white-space:pre-wrap` in the reader wraps at spaces only, and
   `.dg-reader{overflow:hidden}` (line 391) **clips** rather than scrolls, so long PDF lines are
   silently truncated with no way to read them.
   Fix: `.dg-page p{overflow-wrap:anywhere}`.
4. **Plain wiki `<table>`** (line 65) — `width:100%` with auto layout and no wrapper. The worst
   offender is line 803, `<code>http://&lt;host&gt;:11434</code>` in a two-column table; several
   others carry unbreakable `code` tokens. There is no `.md-tablewrap` equivalent for the static
   wiki tables.
   Fix: `@media (max-width:800px){ table{display:block;overflow-x:auto} td code{overflow-wrap:anywhere} }`.

And the structural guard, which is worth adding regardless:

```css
.layout, main { min-width: 0 }
```

### P3 — Overlays: no scroll lock, no focus management, no dialog semantics

Three overlays, all with the same gaps.

| Overlay | Escape | Scrim click | Scroll lock | Focus in | Focus return | Trap | `role="dialog"` |
|---|---|---|---|---|---|---|---|
| Drawer (`nav.side` + `#scrim`) | yes (1382) | yes (1381) | **no** | **no** | **no** | **no** | **no** |
| Reader (`.dg-reader` + `.rd-scrim`) | yes (2513) | yes (2515) | **no** | **no** | **no** | **no** | **no** |
| Companion (`.cmp`) | yes (2670) | n/a (no scrim) | **no** | yes (2665) | **no** | **no** | **no** |

The Escape and scrim-click dismissals are all correctly wired — credit where due. What is
missing is everything else.

- **Background scrolls behind the drawer and the reader.** On a phone, flicking the scrim scrolls
  the page underneath instead of doing nothing, and closing the drawer leaves you somewhere else.
  Fix in `openDrawer`/`closeDrawer` (1379–1380) and in `openDoc`'s `close` (2510):
  ```js
  function openDrawer(){ ...; document.body.style.overflow='hidden'; }
  function closeDrawer(){ ...; document.body.style.overflow=''; }
  ```
- **Focus is never moved into an overlay and never returned.** After closing the reader, focus is
  on a `document.body` with no memory of the "Read" button that opened it.
  ```js
  const opener = document.activeElement;
  const close = () => { ...; opener?.focus(); };
  ```
- **No `role="dialog" aria-modal="true"`** on `.dg-reader` or `nav.side.open`, and no `inert` on
  the background, so a screen-reader user swipes straight through the overlay into the page behind.
  `.dg-reader` also has no labelled name; it already renders an `<h2>` (line 2509) — give it an
  `id` and point `aria-labelledby` at it.

**z-index ordering** (see also P9): `.scrim` 24 → `nav.side` 25 → `.topbar` 30 → `.cmp-fab` 40 →
`.cmp` 41 → `.rd-scrim` 50 → `.dg-reader` 51 → toast 60. The reader correctly outranks everything.
But `.cmp-fab` at 40 sits **above** the drawer scrim at 24, so the "Ask the brewer" button floats
on top of a supposedly-modal overlay and remains tappable — opening the companion (41) on top of
the still-open drawer (25).
Fix: hide it while the drawer is open — `nav.side.open ~ .cmp-fab, body.drawer-open .cmp-fab{display:none}`,
or move the scrim above the FAB.

### P4 — Contrast: `--ink-faint` fails everywhere, and white-on-accent fails in dark

Computed WCAG 2.1 ratios (sRGB relative luminance), all combinations that matter:

**Light theme**

| Foreground | on `--panel` #fff | on `--panel-2` #f6f2ec | on `--bg` #efece5 |
|---|---|---|---|
| `--ink` #241f1a | 16.33 ✓ | 14.64 ✓ | 13.84 ✓ |
| `--ink-soft` #6d6358 | 5.87 ✓ | 5.27 ✓ | 4.98 ✓ |
| **`--ink-faint` #9c9184** | **3.09 ✗** | **2.77 ✗** | **2.62 ✗** |
| `--accent` #a8621f | 4.74 ✓ | **4.25 ✗** | **4.02 ✗** |
| `--good` #3c8f54 | **4.00 ✗** | **3.59 ✗** | **3.39 ✗** |
| `--warn` #bd8a1f | **3.08 ✗** | **2.76 ✗** | **2.61 ✗** |
| `--t-purge` #b5851b | **3.31 ✗** | **2.97 ✗** | **2.81 ✗** |
| `--t-vacuum` #1a8d7d | **4.08 ✗** | **3.66 ✗** | **3.46 ✗** |
| `--t-start` #c6552f | **4.43 ✗** | **3.97 ✗** | **3.75 ✗** |
| `--line-2` #cfc6b6 | **1.69 ✗** | **1.52 ✗** | **1.43 ✗** |

**Dark theme** — much better. Every semantic colour passes (5.07–8.18 on `--panel`). Only two fail:

| Foreground | on `--panel` #221d18 | on `--panel-2` #1c1712 | on `--bg` #171310 |
|---|---|---|---|
| **`--ink-faint` #766a5b** | **3.17 ✗** | **3.37 ✗** | **3.50 ✗** |
| `--line-2` #43392f | **1.48 ✗** | **1.58 ✗** | **1.64 ✗** |

Consequences, in order of impact:

1. **`--ink-faint` fails 4.5:1 in both themes, at every background.** It is not decorative — it
   carries text at 9.5–11.5px: `.stu-idx`, `.br-meta`, `.stu-why`, `.stu-status`, `.stu-foot`,
   `.dg-citehead`, `.dg-page .n`, `.stu-chipcard .meta`, `nav.side .grp`, `.stat span`, `footer`,
   `.cmp-x`. All well under 18.66px, so 4.5:1 applies, not 3:1. Worst case 2.62:1.
   Fix — darken/lighten the token; these hit 4.5:1 on `--bg` (the hardest case):
   ```css
   :root{ --ink-faint:#7f7466 }                 /* 4.54 on #efece5 */
   @media (prefers-color-scheme:dark){:root{ --ink-faint:#9a8d7c }}   /* 5.55 on #171310 */
   ```
   (and the same two values in the `:root[data-theme="light"]` / `["dark"]` blocks, lines 23–24).
2. **White on `--accent` is 2.93:1 in dark mode.** This is `.btn.primary` (line 91), `.dg-q`
   (line 346) and `.stu-msg.me .stu-bubble` (line 229) — the primary action button and every
   message the user has sent, all at 13–13.5px. It passes at 4.74:1 in light and fails in dark
   because `--accent` was lightened to `#d0863f` for *text* legibility without rechecking it as a
   *background*. Fix: use `--ink` on the accent fill in dark, or darken the fill:
   ```css
   @media (prefers-color-scheme:dark){
     .btn.primary,.dg-q,.stu-msg.me .stu-bubble{background:#8a4a12;border-color:#8a4a12;color:#fff}
   }
   ```
   (`#fff` on `#8a4a12` = 6.9:1).
3. **`--line-2` at 1.43–1.69:1** is the border of every `.btn` (line 89), `.burger`, `.br-acts
   button`, `.dg-cite button`, `.dg-watch`. WCAG 1.4.11 wants 3:1 for a control's visual boundary;
   these buttons have effectively no visible edge. It is also `.stu-star`'s unfilled colour
   (line 274), so the empty stars in the rating widget are nearly invisible against `--panel` —
   the affordance ("there are five of these, tap one") is lost.
   Fix: introduce a dedicated `--line-3` at ≥3:1 for control borders and for `.stu-star`'s off state.

### P5 — `.br-grid` gives two unusable columns on a phone

```css
@media (max-width:800px){ .br-grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:11px} }  /* 331 */
```

At 360px: `main` padding is 16px each side (line 185) → 328px of track. `auto-fill` at
`minmax(150px,1fr)` fits 2 columns (2×150+11 = 311 ≤ 328), each **158px**. `.br-acts` has
`padding:0 12px 12px` (line 324) leaving 134px for three `flex:1` buttons with two 6px gaps:
**40.6px each**. "Remux" and "Score" at 12px cannot fit and wrap mid-word or clip.
At 390px it is only marginally better (42.5px each).

The desktop breakpoint uses `minmax(232px,1fr)` (line 308) — the mobile override *lowered* the
minimum, which is backwards: less width, not more, is the reason to go single-column.

Fix:

```css
@media (max-width:460px){ .br-grid{grid-template-columns:1fr} }
@media (max-width:800px){ .br-acts{flex-wrap:wrap} .br-acts button{flex:1 1 46%} }
```

### P6 — The step card header is crushed at 360px

```css
.stu-head{display:flex;align-items:center;gap:9px;padding:10px 11px 10px 15px}   /* 143 */
```

No `flex-wrap`. At 360px the card interior is ~276px and the row holds: grip (40px at ≤800,
line 136) + `.stu-idx` (16px) + `.stu-badge` + `.stu-tname` + `.stu-tdesc` + spacer + three
`.stu-ic` at 40px (line 190) — with 7 gaps of 9px. Fixed-width items alone are 40+16+120 = 176px,
gaps 63px = **239px of 276px**, leaving 37px to share between the badge, the type name and the
description. They will shrink to min-content and wrap to several lines each; `.stu-card{overflow:hidden}`
(line 141) clips whatever still does not fit, so the step type becomes unreadable.

Fix — drop the description and let the row wrap on narrow screens:

```css
@media (max-width:480px){
  .stu-head{flex-wrap:wrap}
  .stu-tdesc{display:none}
  .stu-tname{flex:1 1 100%;order:3}
}
```

### P7 — Touch targets under 44×44

Two blanket rules do most of the work and are worth crediting:
`@media (pointer:coarse){ button,.btn,.stu-add{min-height:42px} }` (line 207) and the ≤800px
enlargements at lines 187–193. What they miss:

| Control | Computed touch size | Why it slips through | Line |
|---|---|---|---|
| `.dg-watch` ("Watch ↗" on video citations) | ~86 × **24px** | It is an `<a>`, not a `<button>`, so line 207 does not apply. Its sibling "Read" `<button>` gets 42px — the two sit side by side at different heights. | 376–377 |
| `.stu-describe > summary` ("…or describe it in words") | full width × **~28px** | `<summary>` is neither `button` nor `.btn` | 296–297 |
| `.stu-chipcard .del` (delete a saved recipe) | **~17 × 42px** | `padding:0 4px`, `font-size:14px`; only `min-height` is set, never `min-width` — and it is a *destructive* action 7px from "load" | 525 |
| `.stu-tog` (boolean step fields, e.g. `ap`) | full width × **~23px** | The `<label>` is the target; `padding-top:3px` + one 12.5px line | 163–164 |
| `.stu-seeall` ("See all →") | ~62 × **19px** | An `<a>` in a `.zone-head` | 515 |
| `.stu-ic` (↑ ↓ ✕ on every step) | **40 × 42px** | `width:40px` set, `min-height:42px` inherited — 4px short on both axes | 190, 205, 207 |
| `.stu-star` | **~28–35 × 42px** | Width comes from the glyph plus 1–4px padding | 191, 206, 274 |

Fix — extend the coarse rule to cover links-as-buttons and constrain width, not just height:

```css
@media (pointer:coarse){
  button,.btn,.stu-add,.dg-watch,.stu-seeall,.stu-describe>summary{
    min-height:44px; display:inline-flex; align-items:center;
  }
  .stu-ic,.stu-star,.stu-chipcard .del{min-width:44px;min-height:44px}
  .stu-tog{min-height:44px}
}
```

### P8 — Step-field inputs have no accessible name

```js
const lab = document.createElement("label");
lab.innerHTML = `<span>${f.label}</span>${f.unit?`<span class="u">${f.unit}</span>`:""}`;
const inp = document.createElement("input");
...
cell.append(lab, inp);                     // 1487-1497
```

The `<label>` is a **sibling** of the `<input>`, not an ancestor, and has no `for`. Every
number field in the builder — temperature, fill volume, vacuum kPa, hold time — is announced as
an unlabelled edit field, and tapping the visible label does not focus it (a real loss at
10.5px on a phone).

By contrast, the Settings form does this correctly by wrapping (`<label class="setrow"><span>Provider</span><select>…`,
lines 766–775) — so the pattern already exists in the file.

Fix:

```js
inp.id = `stu-${i}-${f.k}`;
lab.htmlFor = inp.id;
```

### P9 — The topbar paints over the open drawer

`.topbar{position:sticky;z-index:30}` (line 173) versus `nav.side{position:fixed;…;z-index:25}`
(line 182). The topbar is 65px tall (10px padding + 44px burger + 10px + 1px border) and
full-width, so when the drawer slides in, its top 65px — the whole `.brand` block (line 544,
occupying roughly y=20–54) — is painted over. The scrim (z 24) is also below the topbar, so the
topbar alone stays undimmed while everything else darkens.

Keeping the burger tappable above the scrim is defensible; hiding the drawer's own header is not.

Fix — raise the drawer above the topbar and let the burger sit inside the drawer's stacking order:

```css
@media (max-width:800px){ nav.side{z-index:31} }
```

### P10 — `.bbp` export opens a window after an `await`

```js
const res = await fetch(BASE_URL+"recipes/export-bbp", {...});   // 2112
...
window.open(d.url, "_blank", "noopener");                        // 2119
```

The comment above it is right that the ingress iframe cannot start a download itself. But
`window.open` is called after two `await`s, so the transient user activation from the tap has
expired — Safari blocks this outright, Chrome usually does too. Inside the HA companion app's
webview the outcome is less predictable still.

Fix — do not open programmatically. Have the handler render a real, tappable link and let the
user complete the gesture:

```js
flash(`Wrote ${d.filename}`);
const a = $("stuBbpLink");            // an <a> next to the button, hidden until now
a.href = d.url; a.target = "_top"; a.textContent = `Open ${d.filename} ↗`; a.hidden = false;
```

`target="_top"` navigates the HA shell rather than a blocked popup, which is the reliable route
out of an ingress iframe.

### P11 — Drag-to-reorder cannot cross a screen on a phone

`.stu-grip{touch-action:none}` (line 108) plus `e.preventDefault()` on pointerdown (line 1546)
correctly stop the page scrolling out from under an in-progress drag. But there is no
compensating **edge auto-scroll** in `onGripMove` (1573–1580), and `targetIndex` compares the
live `e.clientY` against `rects` captured once at pointerdown (1520) in viewport coordinates.

Result: on a 360×780 phone a six-step recipe is taller than the viewport, and steps that are
off-screen at the moment the drag begins are simply unreachable — the finger cannot get to them
and the page cannot be scrolled to bring them into view.

The arrow buttons are the documented fallback (comment at line 1606) and do work, so this is
degraded rather than lost — but the grip is the discoverable affordance and it fails silently.

Fix — auto-scroll near the edges and re-measure:

```js
function onGripMove(e){
  if(!drag) return;
  e.preventDefault();
  const pad = 60;
  if(e.clientY < pad)                scrollBy(0, -12);
  else if(e.clientY > innerHeight-pad) scrollBy(0,  12);
  drag.rects = drag.els.map(el=>el.getBoundingClientRect());   // rects go stale once we scroll
  ...
}
```

(Note `drag.card`'s own rect must be excluded from the re-measure, since it is mid-transform.)

---

# Polish

### L1 — ~70 lines of CSS duplicated inside a media query

Lines **409–477** are a byte-for-byte copy of lines **336–407** (`.ask-*`, `.dg-*`, `.md-*`,
`.rd-scrim`, `.dg-reader`, `.setmodel`), nested inside `@media (max-width:600px){` opened at
line 408 and closed by the `}}` at line 478. The only intentional content in that block is the
first declaration (`.setrow{grid-template-columns:1fr;gap:4px}`) and the last
(`.setrow input,.setrow select{font-size:16px;padding:12px}`). Everything between is an
accidental paste — including a nested `@media (max-width:800px)` at line 468.

It renders identically today (same values, same order), so there is no visual bug. The hazard is
maintenance: any future edit to the canonical copy at 336–407 will **not** take effect below
600px, because the duplicate appears later in the stylesheet at equal specificity inside a
matching media query. That is a silent, breakpoint-specific regression waiting to happen.

Fix — delete lines 409–477, leaving:

```css
@media (max-width:600px){
  .setrow{grid-template-columns:1fr;gap:4px}
  .setrow input,.setrow select{font-size:16px;padding:12px}
}
```

### L2 — ARIA gaps

- **`role="radiogroup"` with `<button>` children** (line 896; buttons built at 2054–2058). A
  `radiogroup` requires `radio` children; `<button>` is not one, and nothing carries
  `aria-checked`, so the current rating is announced only through the visual `.on` class.
  Fix: `b.setAttribute('role','radio')` and, in `paintStars()`, `b.setAttribute('aria-checked', String(idx < userRating))`.
  Add roving `tabindex` and arrow-key handling, or switch to real `<input type=radio>` — the
  latter also gets keyboard behaviour for free.
- **No `aria-live` anywhere in the file** (0 occurrences). The toast (1632), `#setMsg` (786),
  `#nlOut` (859), `#askCount` (726) and `.stu-status` all announce results silently.
  Fix: `<p class="stu-hint" id="setMsg" role="status">`, and give the toast
  `t.setAttribute('role','status')` on creation.
- **`.stu-grip` is a `<div>` with `aria-label`** (1464–1465). `aria-label` on a generic element
  with no role is ignored by most AT. Harmless (the arrows are the accessible path), but the
  attribute is doing nothing. Either give it `role="button" tabindex="0"` with keyboard reorder,
  or `aria-hidden="true"` to be honest about it.

### L3 — No `color-scheme` declaration

`<head>` (lines 3–6) has no `<meta name="color-scheme" content="light dark">` and no
`:root{color-scheme:…}`. The CSS themes everything the author drew, but the UA does not know the
page is dark, so `<select>` dropdown popups, the `<input type=password>` reveal control,
scrollbars, and the `<input type=number>` spinners all render light-on-dark. And because the
theme button sets `data-theme` manually (1387–1392), the OS-level `prefers-color-scheme` signal
can be the opposite of what is displayed.

Fix:

```css
:root{color-scheme:light dark}
:root[data-theme="light"]{color-scheme:light}
:root[data-theme="dark"]{color-scheme:dark}
```

### L4 — `prefers-reduced-motion` coverage is partial

The two blocks that exist (line 51 for the section fade, lines 131–135 for the drag transitions,
shifted cards, gap and settle animation) cover exactly the things the brief asked about — that
part is done properly. Not covered:

- `nav.side{transition:transform .22s ease}` (line 183) — the full-screen drawer slide, the
  largest motion in the UI.
- `.stu-fill{transition:width .3s,background .3s}` (245), `.stu-scorebar>i{transition:width .4s}` (262).
- `.br-card{transition:border-color .15s,transform .06s}` (310).

Fix — extend the block at 131:

```css
@media (prefers-reduced-motion:reduce){
  nav.side,.stu-fill,.stu-scorebar>i,.br-card{transition:none}
}
```

### L5 — `outline:none` with no `:focus-visible` replacement

Six rules strip the focus ring from inputs: lines 162, 237, 249, 279, 407, 504. There is **no
`:focus-visible` rule anywhere in the file** (0 occurrences). The replacement is a border-colour
change to `--accent` — which is 4.74:1 against `--panel` in light and 5.70:1 in dark, so it is
*visible*, but it is a 1px border and it is the only cue. Buttons keep their UA ring (none of
them set `outline:none`), so the treatment is inconsistent across the form.

Fix — replace the outline rather than remove it:

```css
:where(input,select,textarea,button,a,summary):focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}
```

### L6 — Dead space to the right of `main` on wide screens

`main{max-width:820px}` (line 44) inside a `1fr` grid track. At 1440px the track is 1210px and
`main` occupies the leftmost 820px, leaving ~390px empty. A measure cap is right for the wiki
prose, but it also caps the studio's `.stu-side` (line 169, `auto-fit minmax(268px,1fr)` → 3
columns max) and the browse grid at 3 cards on a screen that could hold 5.

Fix — centre it, and let the two grid-heavy pages breathe:

```css
main{margin-inline:auto}
main:has(> #studio.on), main:has(> #browse.on){max-width:1200px}
```

### L7 — Near-miss touch targets

Covered in the P7 table: `.stu-ic` at 40×42 and `.stu-star` at ~28–35×42 are the two that are
*close* rather than wrong. Worth fixing with the same rule, but they are not what breaks a phone.

### L8 — Toast overlaps the FAB at 360px

The toast (line 1636) is `bottom:20px; left:50%; translateX(-50%)`. "Copied save_recipe call" at
13px/600 plus 32px padding is roughly 207px wide, spanning x=76–283 on a 360px screen. The FAB
at ≤800px is `bottom:16px; right:16px` with `padding:13px 18px; font-size:14px` (line 198) —
roughly 150px wide, spanning x=194–344. They overlap by ~90px, and the toast (z 60) wins over
the FAB (z 40).

Fix: `bottom:20px` → `bottom:76px` inside the `@media (max-width:800px)` block, so the toast
clears the FAB.

---

# Handled well

Stated explicitly so these are not re-litigated:

- **`<meta name="viewport" content="width=device-width, initial-scale=1">`** (line 5) — no
  `maximum-scale`, no `user-scalable=no`. Pinch zoom works. This is the correct value.
- **`.md-tablewrap{overflow-x:auto}` + `.md-table{min-width:420px}`** (361–362) — the right way to
  contain a wide table. The Diagnose answers, the most table-heavy surface, are safe.
- **`pre{overflow-x:auto}`** (line 61) — contains the ASCII architecture diagram (1011–1018) and
  the YAML blocks without touching page width.
- **`touch-action:none` on `.stu-grip`** (line 108) with Pointer Events for one code path across
  mouse/pen/touch — the correct primitive, and the comment at 104–106 explains why.
- **Arrow buttons kept alongside drag** (comment at 1606) so reordering survives without a pointer.
- **`aria-label` on every icon-only control**: `.burger` (538), `.stu-ic` ↑↓✕ (1609),
  `.stu-chipcard .del` (2013, and it interpolates the recipe name), `.stu-star` (2056),
  `.cmp-x` (1338), `.stu-grip` (1465). This is more thorough than most codebases.
- **Every top-level `<input>`/`<select>` has a name** — `aria-label` on 702, 703, 733, 778, 782,
  856, 893, 899, 1344; wrapping `<label>` on 766–775.
- **Escape and scrim-click dismiss on both the drawer and the reader** (1381–1382, 2513–2515).
- **`prefers-reduced-motion` on the drag animation and the section fade** (51, 131–135) — the two
  the brief called out, both correct.
- **`.br-bar input{flex:1 1 200px;min-width:0}` with `flex-wrap`** (303–306) — a correctly
  shrinkable flex row.
- **Dark theme colour work** — every semantic token (`--good`, `--warn`, `--t-*`, `--accent`)
  clears 5:1 on `--panel` in dark. The light theme is the one that needs attention, which is the
  reverse of the usual failure.
- **`hidden` attribute usage** — `#scrim` (541) and `#askReader` (740) set `position:fixed` without
  setting `display`, so the UA `[hidden]{display:none}` rule still applies. Correct.

---

# Not determinable without rendering

1. **Exact button heights.** `<button>` defaults to `line-height:normal`, which varies by font and
   platform. Every "computed height" above assumes ~1.2. The 42-vs-44 calls in P7/L7 are within
   that margin; the 24px and 28px ones are not.
2. **Whether the clipboard works at all even over HTTPS.** `navigator.clipboard.writeText` from a
   cross-origin iframe needs `allow="clipboard-write"` on the iframe element. Whether Home
   Assistant's ingress iframe delegates that permission cannot be read from this file. If it does
   not, B5's `.catch` branch fires on every platform and the "select manually" message is still
   unactionable.
3. **Whether `window.open` (P10) survives the HA companion app's webview** on iOS and Android, and
   whether `/local/bkon/hamenu.bbp` is even reachable from inside ingress.
4. **The exact min-content width of the static wiki tables** (P2 item 4) — it depends on the
   rendered font metrics for the monospace stack, so whether they *actually* overflow at 360px is
   a measurement, not a deduction. The break rules are cheap insurance either way.
5. **Whether the topbar/drawer overlap (P9) is visually obvious** — the 65px topbar height assumes
   the burger renders at its declared 44px with no UA minimums applied.
6. **Real-device iOS keyboard behaviour for B4** — the failure mode is well established for
   `position:fixed`, but the exact amount of the composer that ends up hidden depends on the
   keyboard height and whether the HA webview enables `viewport-fit` / dynamic viewport units.
7. **Focus-order sanity** across the whole page once B3 is fixed and the nav becomes tabbable —
   worth a manual tab-through afterwards.

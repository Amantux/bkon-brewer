# Wiki plan — reorganising around the machine, not the software

A proposal for the add-on wiki (`addon/webroot/index.html`). Nothing here has been
applied; this is the argument and the drafted copy, so the edit is mechanical when
it happens.

## The problem, stated plainly

The wiki has thirteen flat entries behind one collapsed toggle. They are ordered by
what got built: protocol, `.bbp` format, architecture, fidelity. Of those thirteen,
**one** (Units & error codes) is a page anyone consults twice, and it is buried
eleventh in a list that opens with a project overview.

Meanwhile the machine itself — a commercial vacuum brewer with a 111-page service
manual, twelve valves, a dozen temperature-sensor fault codes and a maintenance
regime that is a **warranty condition** — has no pages at all. The one thing a
BKON owner needs at 07:40 on a Tuesday with `C:3 M:5` on the screen is the one
thing the wiki does not have.

Everything below is drawn from the local index of 49 Franke/BKON service documents
(`bkon_brewer_kb.json`) plus the project's own `docs/`. Facts are cited to their
source document and page so each can be re-checked. Nothing is reproduced verbatim
at length.

---

# 1. Proposed navigation

## Primary nav (always visible)

| Entry | Change |
|---|---|
| 🧪 Recipe studio | unchanged |
| 📖 Recipes | unchanged |
| 🩺 Diagnose & docs | unchanged |
| **🚨 Fault finder** | **NEW — promoted to primary** |
| ⚙️ Settings | unchanged |

**Why Fault finder is promoted.** `Diagnose & docs` is a search box: it answers a
question you can already phrase. Fault finder is a *table you scan* — you have a
code on a screen and you want its meaning, its likely cause and the next physical
action, in that order, without typing. Those are different tools and the second one
is the one used under pressure. It is also the only page whose value is entirely
independent of whether the Bluetooth link, the add-on or LightRAG are working,
which is exactly the condition you are in when the machine is broken.

## Group 1 — "Run the machine" *(expanded by default)*

| id | Title | Status |
|---|---|---|
| `daily` | The daily round | NEW |
| `maintenance` | Maintenance calendar | NEW |
| `water` | Water, scale and the warranty | NEW |

Rationale: this is the only group whose pages are read on a schedule rather than in
an emergency. Start-up order, the weekly clean, the descale interval — get these
wrong and you generate the faults in Group 2. Putting them first is a claim about
causality, not just about frequency.

## Group 2 — "When it goes wrong"

| id | Title | Status |
|---|---|---|
| `faults` | Error codes: cause and fix | NEW (also the primary-nav target) |
| `sealed` | Chamber not sealed (`C:3 M:5`) | NEW |
| `flow` | No water (`C:40 M:5`) | NEW |
| `symptoms` | Symptoms with no error code | NEW |
| `service-menu` | Service menu: tests, calibrations, logs | NEW |
| `parts` | Parts, and what to have on hand | NEW |

Rationale: ordered by what happens in time. You read a code, you follow that code's
pathway, and if there is no code you fall through to symptoms. The service menu and
the parts list are the two things every pathway calls into, so they sit at the
bottom as shared references rather than being repeated in each.

`C:3 M:5` and `C:40 M:5` get dedicated pages because the source material makes them
enormously deeper than the rest: between them they account for four dedicated
documents and roughly 90 indexed passages. Every other code fits in a row of the
`faults` table.

## Group 3 — "Understand and design"

| id | Title | Status |
|---|---|---|
| `howitworks` | How the machine works | NEW |
| `rain` | Designing a RAIN recipe | NEW |
| `reference` | Units, ranges and limits | KEPT, trimmed |
| `menufile` | Menu files and longer recipes | MERGE of `longer` + `bbp` |

Rationale: this is the "I have ten minutes and I want to be better at this" group.
`howitworks` exists to build intuition, not to fix anything — knowing that the
first three seconds of every brew are a seal check makes half of Group 2 obvious
rather than memorised.

## Group 4 — "About this project" *(collapsed)*

| id | Title | Status |
|---|---|---|
| `overview` | What this is | KEPT, demoted and trimmed |
| `quickstart` | Quick start | KEPT |
| `hass` | In Home Assistant: entities & services | MERGE of `entities` + `services` |
| `recipes` | Recipes, files and git | KEPT |
| `concierge` | Asking questions (concierge + semantic Q&A) | MERGE of `concierge` + `rag` |
| `protocol` | Protocol, provenance and fidelity | MERGE of `protocol` + `architecture` + `fidelity` |

Rationale: every page here is read once, during setup or out of curiosity, and
never again. That is the definition of a collapsed group. None of them is deleted —
`protocol` in particular is the most rigorous thing in the repository — but none of
them belongs above a page that tells you why your beverage is not purging.

## Full mapping of the existing thirteen

| Existing id | Goes to | Note |
|---|---|---|
| `overview` | About → `overview` | Demoted. Trim the architecture diagram in from `architecture`. |
| `quickstart` | About → `quickstart` | Unchanged. |
| `entities` | About → `hass` | Merged. |
| `services` | About → `hass` | Merged. |
| `concierge` | About → `concierge` | Absorbs `rag`. |
| `recipes` | About → `recipes` | Unchanged. |
| `longer` | Understand → `menufile` | Merged. |
| `architecture` | About → `overview` | **Dissolved.** See cuts. |
| `protocol` | About → `protocol` | Absorbs `architecture` residue and `fidelity`. |
| `rag` | About → `concierge` | Merged. |
| `reference` | Understand → `reference` | **Split**: the error table moves to `faults`; units stay. |
| `bbp` | Understand → `menufile` | Merged. |
| `fidelity` | About → `protocol` | Merged. |

Net: 13 flat entries → 4 primary + 19 grouped, of which 12 are new and 6 are the
survivors of merging 9 old ones.

---

# 2. New pages

Each page below is drafted in full. Source citations are inline in the form
*[Document name, p N]* so any claim can be checked against the index. A key to the
documents is at the end.

Two conventions I have used throughout, and recommend keeping in the rendered
pages:

- **Anything the sources disagree about is called out as a disagreement**, not
  silently resolved. There are five such conflicts and each one is a place where
  acting on the wrong number wastes an afternoon.
- **Anything inferred is labelled.** The service documents are unusually concrete;
  where I have joined two of them together, I say so.

---

## 2.1 `faults` — Error codes: cause and fix

**Who needs it and when.** Anyone standing at the machine with a code on the
screen. Also the integration itself: `sensor.*_last_error` renders a label, and
this page is where the label's meaning lives. It should be readable in ten seconds
by someone who is annoyed.

### Draft

> ### Error codes: cause and fix
>
> The brewer reports faults as a pair — `C:` a code, `M:` a module. The module
> number matters: `C:20 M:2` and `C:20 M:5` are different faults. Codes in module 2
> are informational; codes in module 5 are hardware.
>
> #### The whole table
>
> | Code | On screen | What it actually means | First thing to do |
> |---|---|---|---|
> | `C:1 M:5` | Brew Chamber Glass | The brew-cylinder switch is not reading. Cylinder missing, mis-seated or damaged; or the switch or its wiring has failed. | Remove and reinstall the brew chamber. |
> | `C:2 M:5` | Brew Handle | The brew handle was not detected. | Make sure a handle and basket are in place before brewing. |
> | `C:3 M:5` | Chamber not Sealed | A vacuum cannot be created in the chamber. Nine documented causes. | [Chamber not sealed →](#sealed) |
> | `C:11–C:22 M:5` | Temperature Sensor | A temperature check failed. The code identifies which sensor and how. | Restart, then use the sensor table below. |
> | `C:40 M:5` | Flow Meter | No water flow — or under 4 ml/s — detected. | [No water →](#flow) |
> | `C:50 M:5` | LIM Communication | The main board is not receiving values from the LIM board. | Restart. Never touch the comms cable with the power on. |
> | `C:20 M:2` | Information Missing | The recipe data is incomplete. | Restart and select a different brew. |
> | `C:30 M:2` | Information Code | The brew data is wrong. | Update the menu file. |
> | `C:45 M:2` | Descale Finished | Not a fault. The descale cycle completed. | Press RESTART. |
>
> *Sources: [Error Codes, p2] for the code list and modules; [Error Codes, p3–p40]
> for the per-code causes; [Service Provider Training (Part I), p54] for `C:2 M:5`;
> [Troubleshooting - StepByStep App, p4] for the flow-meter trigger threshold.*
>
> **`C:2 M:5` is not in the Error Codes reference.** It appears only in the service
> training deck's error table [Service Provider Training (Part I), p54], and the
> Service Manual and Troubleshooting Guide both describe the fault ("Brew Handle
> not detected") without giving its code [Service Manual, p56; Troubleshooting
> Guide, p2]. It is real; it is just missing from the document everyone treats as
> the master list. This project's error table should carry it.
>
> #### The temperature sensors, one code at a time
>
> `C:11`–`C:22` are usually written off as "a temperature sensor". They are not
> interchangeable: the code tells you which sensor, whether it failed short or
> open, and which half of the machine to open.
>
> | Code | Sensor | Failure | Where |
> |---|---|---|---|
> | `C:11` | Thermoblock 1 | short | WVSC |
> | `C:12` | Thermoblock 2 | short | WVSC |
> | `C:13` | Thermoblock 3 | short | WVSC |
> | `C:14` | Cold water | short | WVSC |
> | `C:15` | Hot water | short | Tower |
> | `C:16` | Mix water | short | Tower |
> | `C:17` | Thermoblock 1 | open — or the incoming water is simply too cold | WVSC |
> | `C:18` | Thermoblock 2 | open | WVSC |
> | `C:19` | Thermoblock 3 | open | WVSC |
> | `C:20` | Cold water | open — or incoming water too cold | WVSC |
> | `C:21` | Mix water | open | Tower |
> | `C:22` | Hot water | open | Tower |
>
> *Source: [Service Manual, p58].*
>
> Three things follow from that table that the one-line version hides:
>
> - **`C:17` and `C:20` may not be faults at all.** Both carry "or incoming water
>   is too cold" as an alternative reading. A cold-morning open-circuit report on
>   thermoblock 1 or the cold-water sensor is worth re-testing warm before ordering
>   a sensor.
> - **A short and an open are different repairs.** `C:11` and `C:17` are the same
>   sensor; one is a pinched or chafed harness, the other a broken connection.
> - **Tower or WVSC tells you which cabinet to open** before you take a single
>   screw out. `Thot` sensor wires are green, `Tmix` grey [Service Manual, p17].
>
> The documented procedure for all twelve is the same and short: restart the
> machine; check the sensor; replace the sensor [Error Codes, p41].
>
> #### Two places the sources contradict each other
>
> **Which code is the mix-water sensor.** The Error Codes reference lists the
> temperature bank as 11, 12, 13, 16, 17, 18, 19, 22 and labels `C:16` "T-mix
> short" and `C:22` "T-mix open" [Error Codes, p2, p41]. The Service Manual lists
> all twelve codes and makes `C:21` the mix-water open and `C:22` the hot-water
> open [Service Manual, p58]. The Service Manual is the more specific document and
> is internally consistent across twelve rows; the Error Codes deck omits 14, 15,
> 20 and 21 entirely. **Use the Service Manual table.** If you are chasing `C:22`,
> check the hot-water sensor in the tower first and the mix sensor second.
>
> **"Information Missing".** The Error Codes summary table gives it as `C:20 M:2`;
> the detail slide three pages later heads the same fault `C:50 M:5`, which is the
> LIM communication code [Error Codes, p2 vs p38]. That is a typo on the detail
> slide. Take the summary table.
>
> #### Before you call anyone
>
> Whatever the code, four things make the difference between a diagnosis and a
> guess, and all four are free [No Problem Found, p1]:
>
> 1. Photograph the `i` screen. It carries the UI version, main board firmware,
>    menu file name and the brew, descale and clean-in-place counters
>    [Accessing Programming, p50].
> 2. Confirm the software is current. "Software is not up to date" is a documented
>    cause of `C:3 M:5` in its own right [Error Codes, p16].
> 3. Take a water reading — TDS and grains per gallon. See [Water →](#water).
> 4. View and export the error log from the Administration menu. It is timestamped
>    [Accessing Programming, p18–p20].

---

## 2.2 `sealed` — Chamber not sealed (`C:3 M:5`)

**Who needs it and when.** The single most common and most involved fault in the
whole archive: seven passages of a dedicated per-fault document, ten of a dedicated
vacuum-leak document, and roughly thirty slides of the step-by-step troubleshooting
app. It deserves a page because the correct order of investigation is
counter-intuitive and running it out of order costs hours.

### Draft

> ### Chamber not sealed — `C:3 M:5`
>
> The machine reports this when it cannot create or detect a vacuum in the brew
> chamber at the start of a recipe [Brew Chamber not Closed Error, p1;
> Troubleshooting - StepByStep App, p37]. It is not a warning about the beverage;
> the brew never starts.
>
> **Why it fires so early.** The first three seconds of every beverage cycle are a
> seal check — the machine pulls a small "preparation vacuum" before any water
> enters, for two reasons: to verify there is no air leak, and to leave a pressure
> buffer so that the first water in does not flash to steam and over-pressurise the
> cylinder [Service Manual, p78; Troubleshooting - StepByStep App, p54]. `C:3 M:5`
> is that check failing.
>
> #### Work outward, not inward
>
> Nine causes are documented. They are listed here in the order the cost of
> checking them increases, which is not the order any single source presents them:
>
> | # | Cause | Fix |
> |---|---|---|
> | 1 | Locking handle is not fully down | Check basket and handle alignment, then lock the handle down [Error Codes, p12] |
> | 2 | Debris on a gasket | Clean every rubber gasket on the baskets and the chamber and confirm a seal [Error Codes, p6] |
> | 3 | Plunger gasket twisted or damaged | Remove the chamber, inspect the orange/red plunger seal, reseat or replace [Error Codes, p6; Brew Chamber not Closed Error, p1] |
> | 4 | Purge valve stuck open | Poke it with the purge valve tool; run two manual rinses to flush debris; disassemble, rinse, reassemble; replace [Error Codes, p9] |
> | 5 | Software out of date | Compare UI and main board versions against the current release and update [Error Codes, p16–p17] |
> | 6 | Bad data-cable connection | Check the communication cable at both the tower and the WVSC [Error Codes, p14] |
> | 7 | Debris in the vacuum pump or its lines | Clean or replace the pump; check the vacuum lines; check the recipes [Error Codes, p18] |
> | 8 | Air leak in the tower | Negative pressure test, then the bypass ladder below |
> | 9 | Air leak in the WVSC | Negative pressure test, then inspect V10 port 1, V9 port 1 and the vacuum pump fittings, and the 6 mm tubing between them [Brew Chamber not Closed Error, p1] |
>
> One physical check belongs with cause 7 and is easy to miss: **the water level in
> the brew chamber should never reach the plunger assembly** [Error Codes, p19]. If
> it does, a recipe is over-filling and the pump is drinking water.
>
> #### The operation check, in one pass
>
> Before any test equipment, walk the seal path [Brew Chamber not Closed Error, p1]:
> basket rubber seal, portafilter edges and bottom, portafilter magnet present,
> brew cylinder top and bottom rubber rings, the red plunger seal for twist or
> damage, the purge valve. Then make a drink.
>
> #### Is it the purge valve? A ten-minute test
>
> Log into the service menu (PIN 4576), tape over the hole in the portafilter, and
> run **Field → Purge Test** [Troubleshooting - StepByStep App, p50–p52]:
>
> - Value **20–25** — the purge valve is fine. Remove the tape and move on.
> - Value **below 19** — the purge valve is leaking. Clean or replace it.
> - Value **above 25** — the purge valve is blocked. Replace it.
>
> Remove the tape afterwards. Then re-run the positive pressure test without the
> tape; if it now fails, inspect the basket and the brew chamber rings
> [Troubleshooting - StepByStep App, p53].
>
> **A conflict worth knowing about.** The service training deck states the purge
> test range as 16–22 kPa [Accessing Programming, p30]; the step-by-step app says
> the UI returns a value between 10 and 50 and that a good valve reads 20–25
> [Troubleshooting - StepByStep App, p51]. The two overlap but do not agree. The
> step-by-step app is the later, more procedural document and is the only one that
> tells you what *direction* a bad reading means, so use its numbers — but treat
> anything between 16 and 25 as ambiguous rather than confirmed good.
>
> #### Finding an air leak by bypassing it
>
> If the seal is good and the purge valve tests clean, the leak is in the air path.
> The technique is the same in three separate documents: close the flow regulator
> FR2, then run a 6 mm tube from the input of the vacuum pump (M2) directly to each
> point along the air path in turn, and re-run the test — or simply try to make a
> beverage. **The first connection at which the machine works puts the leak between
> that point and the previous one.** [Vacuum Leak, p2–p13; Brew Chamber not Closed
> Error, p11–p12; Troubleshooting - StepByStep App, p54–p64]
>
> Work along the path in this order:
>
> 1. M2 input → air/water separator output
> 2. M2 input → the air port of the CHAD fitting on the WVSC
> 3. M2 input → the air port of the CHAD fitting under the tower
> 4. M2 input → port 2 of the atmosphere valve V6, on top of the tower
> 5. M2 input → the T-fitting going to the brew chamber
> 6. M2 input → the fitting on the pressure sensor
>
> The air path in the tower, in physical order, is: brew chamber → T to the pressure
> sensor → atmosphere valve V6 → down through the tower's air CHAD port → the WVSC →
> flow regulator FR2 → vacuum pump M2 [Vacuum Leak, p9, p11, p13]. Reading the list
> above against that path is what makes the bisection make sense.
>
> #### The one mechanical cause people miss
>
> With the locking handle **up**, check for left-and-right play in it. If there is
> any, the four screws on the left and right axle clamps that carry the handle have
> loosened — remove them, apply thread lock, reinstall [Brew Chamber not Closed
> Error, p1]. A handle that rocks does not load the chamber evenly and no amount of
> gasket replacement fixes it.
>
> #### If nothing is found
>
> Run the negative pressure test on the tower; if it is clean, run it on the WVSC;
> if that is clean too, the fault is not an air leak and it is time to call
> support — with the exported error log [Brew Chamber not Closed Error, p1–p2].
>
> **Parts to have before you start** (the documented truck stock for this fault):
> 3/2-way ¼" valve `19006201`, plunger seal gasket `19006258`, brew chamber
> silicone rings `19006265` (×2), long portafilter purge valves `19006305` (×4),
> pressure switch `19006430`, low-voltage board `19006431`, glass brew pipe
> `19006590`, 6 mm plastic tubing `19006160` [Brew Chamber not Closed Error, p2].

---

## 2.3 `flow` — No water (`C:40 M:5`)

**Who needs it and when.** The other fault with a dedicated document and its own
branch of the step-by-step app. It also has the best property of any fault in the
set: most of its causes are outside the machine, and can be ruled out without
opening anything.

### Draft

> ### No water — `C:40 M:5`
>
> The flow meter is not seeing water move. The documented trigger is **flow below
> 4 ml/s** [Troubleshooting - StepByStep App, p4]. For scale: a recipe consumes
> about **20 ml/s** [Pre-Installation Checklist, p6].
>
> #### Rule out the room first
>
> Five checks, none of which requires a tool [Flow Meter Error, p1;
> Troubleshooting - StepByStep App, p7–p8]:
>
> 1. **Is the water valve to the unit on?** [Error Codes, p22]
> 2. **Are the two drains separate?** The tower drain and the WVSC drain must each
>    run to the store drain, never to each other. Hooking them together is a
>    documented cause of this exact error, and it is a common installation mistake
>    [Error Codes, p29; Flow Meter Error, p1; Installation Manual, p9].
> 3. **Is the supply pressure 30–90 psi, static and dynamic?** Below 30 psi, boost
>    it [Flow Meter Error, p1].
> 4. **Does the machine share a line?** Turn off every other appliance on the
>    BKON's water line and retry. If it works with them off, the brewer needs a
>    dedicated line [Error Codes, p24].
> 5. **Is there air in the lines?** Power cycle and let it reboot to purge air.
>    Repeat up to four times before concluding anything [Error Codes, p34].
>
> Then the filter: an RO or filtration system that is clogged, off or failing
> starves the machine [Error Codes, p24]. And the sieve — there is a screen between
> the water inlet fitting and the main valve V1, part `19006264`; clean or replace
> it [Error Codes, p25; Flow Meter Error, p1].
>
> #### Watch the water, timed
>
> The most efficient test in the archive. Let the machine cool (run **Cool Down**
> first — the system is full of hot water under pressure), disconnect the C and H
> lines at the base of the tower into a bucket, and turn the machine on
> [Troubleshooting - StepByStep App, p9–p12; Flow Meter Error, p1]:
>
> | Window | What you should see |
> |---|---|
> | 0–15 s | Water on **C** only — first weak (city pressure), then strong when the pump starts |
> | 16–20 s | Strong flow on **H**, and none on **C** |
>
> That pattern is the initialization sequence made visible: V1 and the mixing valve
> V5 open first and push cold water to drain; the pump M1 and the brewing valve V11
> join in; then V5 closes and everything goes through the hot side [AIR and WATER
> FLOW, p4–p6]. If the pattern breaks, you now know *which half* is at fault before
> touching a component.
>
> Also blow through the disconnected tower drain line D to confirm it is not
> blocked [Troubleshooting - StepByStep App, p13].
>
> #### Then the components, in order
>
> The sequence below is the one the dedicated document uses, and it follows the
> water [Flow Meter Error, p1–p2]:
>
> 1. **Main valve V1** — water at the input? at the output? 24 VDC at the coil? is
>    the coil working?
> 2. **Water pump and motor** — run **Field → Water Calibration**; check for
>    208 VAC at the motor.
> 3. **Flow meter** — water in, water out, harness secure at the meter and the
>    low-voltage board. If the unit has two flow meters, check both for swapped
>    wiring. Also: does water run continuously and overfill the chamber? That is
>    the same fault seen from the other side.
> 4. **Thermoblock TB1** (cold side) — water in, water out.
> 5. **Thermoblocks TB2 and TB3** (hot side) — water in, water out. If water goes
>    in and nothing comes out, they are limescaled.
> 6. **Air sanitizing valve V2**, the overpressure valve, the mixing valve V5, the
>    fill valve V3 and the rinse valve V4 — the same four questions each: water in,
>    water out, 24 VDC, coil live.
>
> #### If it is scale, it is never just the thermoblocks
>
> When limescale is found in TB2/TB3, the documented replacement set is the two
> thermoblocks (`21.210003513`), the air sanitizing valve V2 (`19006226`), the
> overpressure valve (`19006337`), the fill valve V3 and rinse valve V4
> (`19006227`) and the rinser assembly (`18010419`) — because whatever scaled the
> thermoblocks has been through all of them [Flow Meter Error, p2]. The document is
> explicit that the water must then be tested; a water test kit is available from
> technical support.
>
> That is a several-hundred-dollar parts list caused entirely by water chemistry.
> See [Water, scale and the warranty →](#water).
>
> #### Where the restriction usually is
>
> The step-by-step app localises two restrictions by name [Troubleshooting -
> StepByStep App, p16–p17]: restriction at the fill/rinse valves means cleaning or
> replacing valve assembly `18010420`; restriction in the hot tower line means
> cleaning the elbow in the hot line and replacing the overpressure valve.
>
> **Truck stock for this fault:** flowmeter valve `19006173`, 3/2-way ¼" valve
> `19006201`, 2/2-way ⅛" valve `19006226`, 3/2-way ⅛" valves `19006227` (×2),
> safety overpressure valve `19006337`, solenoid water valve `19006421`,
> low-voltage board `19006431`, high/low-voltage board `19006432`, sieve
> `19006264`, PROCON pump motor `19006333`, thermoblock assemblies
> `21.210003513` (×2), rinser assembly `18010419`, water pump `19006332`
> [Flow Meter Error, p3].

---

## 2.4 `symptoms` — Symptoms with no error code

**Who needs it and when.** The machine is misbehaving and the screen is clean. This
is the highest-density page in the whole plan: two source tables plus two slides of
field-note shorthand cover about eighteen distinct symptoms, several of which
appear nowhere else in the archive.

### Draft

> ### Symptoms with no error code
>
> Not everything the machine does wrong announces itself. These are the documented
> symptom→cause pairs, in the order you are likely to meet them.
>
> #### The common table
>
> | Symptom | Likely cause | What to do |
> |---|---|---|
> | User interface does not come on | Main power off, or the communication cable is disconnected | Check the cord and the breaker; check the cable at both the tower and the WVSC |
> | Water leak | Leak between tower and WVSC, leaking drain lines, or a leak inside the WVSC | Check water-line connections, then drain-line connections at the tower, the WVSC and the store drain |
> | The drink did not purge | Purge valve stuck closed | Use manual purge; or remove the valve with the purge valve tool and then manual purge; try a different valve |
> | Purging or dripping *during* the brew | Debris in the purge valve, or a weakened purge valve spring | Clear the ball with the purge valve tool; punch it from inside the brew handle; replace the valve |
> | Beverage level is wrong | Corrupt recipe, or a flow-meter fault | Try a different recipe in the same size first — it separates recipe from hardware in one brew |
> | Consistently poor beverage quality | Wrong dose, out-of-spec water, corrupt recipe, chamber locked during start-up, or wrong temperature | Check the dose and the recipe; check the water; **restart with no basket or handle installed** |
>
> *Source: [Troubleshooting Guide, p2], repeated verbatim in [Service Manual, p57]
> and [Service Provider Training (Part I), p54].*
>
> **That last one is worth pulling out.** If the brew chamber was locked while the
> machine started up, the start-up calibration fails, and the result is not an
> error — it is quietly bad coffee, indefinitely. The fix is a restart with the
> basket and handle out of the tower. This is why the start-up procedure insists on
> it. See [The daily round →](#daily).
>
> #### The field notes
>
> These come from two slides of a service app and are terser than the rest of the
> archive, but they are the only record of several failure modes and they are
> unusually specific about cause [Troubleshooting - StepByStep App, p70–p71]:
>
> | Symptom | Documented cause |
> |---|---|
> | Water leaking on the **right side** | The side check valves that release positive and negative pressure are reversed or leaking |
> | The **left LED** is out | Water has got through a leaking check valve. Replace the check valve, run an air calibration, and replace the left LED cluster |
> | Purging during manual rinse and rinse | Temperature is not being controlled — usually a software problem, and often a wrong language file, so check both the UI and main board versions. Or something is stuck in the purge valve |
> | Manual rinse is not effective | The overpressure valve is leaking, so the line delivers air rather than water and the water takes a long time to arrive |
> | **Squeaking under filling** | The nozzle has scaled up and can no longer return. Replace it, and go looking for other scale damage |
> | Descale cycle will not run through | The descale valve is stuck — the documented reason is that people do not run water through after a descale cycle. **If you do not hear three clicks during boot, the descale valve is not responding** |
> | Water exits at the front | Something inside the WVSC has failed. Turn it off and bring WVSC parts |
>
> Two of those are worth a sentence each because they turn a symptom into a habit:
>
> - **A leaking overpressure valve is a scale symptom, not a valve symptom.** The
>   notes flag it as urgent and tell you to check for major scale damage while you
>   are in there. Combined with the squeaking nozzle, the picture is consistent: in
>   this machine, scale shows up first as *air where water should be*.
> - **The three clicks at boot are a free descale-valve test.** Every start-up
>   tells you whether V13 is alive, for the price of listening.
>
> #### "No problem found"
>
> When the machine misbehaves for the owner and behaves for the technician, the
> archive has a formal protocol for it, and it is a good self-check list too
> [No Problem Found, p1]:
>
> 1. Photograph the `i` screen.
> 2. Confirm the main board and UI software are current.
> 3. Take water readings — TDS and grains per gallon.
> 4. View and export the error log.
> 5. Confirm manual rinse and manual purge both work.
> 6. Brew three deliberately different drinks — a black concentrate, a small green,
>    a large white. Different temperatures, different volumes, different vacuum
>    ladders.
> 7. Inspect the brew baskets, the portafilter, the brew chamber, the plunger
>    gasket and the locking handle.
> 8. Run the negative pressure test on the WVSC; if it is clean, run the positive
>    pressure test on the WVSC. If either shows a leak, run the corresponding tower
>    test.
> 9. In **Field**: vacuum calibration, water calibration, and a purge test on
>    *every* purge valve, cleaning or replacing as needed.
> 10. Run a Clean in Place cycle.
> 11. Then call support.
>
> Step 6 is the clever one. Three drinks chosen at the corners of the parameter
> space exercise more of the machine than a dozen of the same recipe.

---

## 2.5 `maintenance` — Maintenance calendar

**Who needs it and when.** Every owner, forever. This is a *warranty condition*,
not a suggestion, and the archive says so twice on the same page. It also has a
genuine open question — how often to descale — that the sources answer differently,
and resolving it is exactly what a wiki page is for.

### Draft

> ### Maintenance calendar
>
> Failure to clean and descale as instructed **may void the warranty**. That is the
> manufacturer's wording, printed twice in the maintenance guide [Daily / Weekly /
> Monthly Maintenance Guide, p2, p4].
>
> The machine counts what you do: the `i` screen shows brew cycles, descaling
> cycles and clean-in-place cycles [Accessing Programming, p50]. That is the number
> a warranty conversation will turn on.
>
> #### Every day
>
> **Per brew handle** — insert the basket and the handle with the purge valve
> seated, lower the locking lever, and run **two** manual rinse cycles. Repeat for
> every handle [Daily / Weekly / Monthly Maintenance Guide, p1].
>
> **Then the outside** — wipe the exterior surfaces with a clean, damp cloth. Do not
> use excessive moisture, and make sure the drip-tray screen is dry afterwards.
>
> **Then the parts** — wash the accessories. They are dishwasher safe; rinse,
> sanitize and air dry before reassembly.
>
> **At end of service, every day** — make sure the brew chamber is clear of debris.
> If your volume warrants it, wash it more often than weekly.
>
> Add to that the start-up and shutdown ritual, which is short and load-bearing:
> see [The daily round →](#daily).
>
> #### Every week
>
> **Clean in Place** — a four-step guided cycle from the wrench menu: clean, rinse,
> rinse, sanitize. Put one BKON cleaning tablet in the basket, insert and lock the
> handle, put a 32 oz (946 ml) pitcher under the outlet, and follow the screen. An
> operator must be present to empty the pitcher when prompted, three times. **The
> water is extremely hot** [Daily / Weekly / Monthly Maintenance Guide, p2;
> Accessing Programming, p4].
>
> On-screen instructions vary by software version. Follow the screen, not the
> printed guide, where they differ — the guide says so itself.
>
> **Purge valves — the overnight soak.** After the wash cycle, remove every purge
> valve with the purge valve tool. Dissolve one cleaning tablet in a 32 oz pitcher
> of hot water. Poke each valve with the tool, drop them in, and leave them
> overnight. Rinse thoroughly in the morning, reinstall with the tool — *do not
> overtighten* — and run one manual rinse per handle [Daily / Weekly / Monthly
> Maintenance Guide, p3].
>
> This is the single highest-leverage maintenance task on the machine. A dirty or
> sticky purge valve is a documented cause of `C:3 M:5`, of drinks that will not
> purge, of dripping mid-brew, and of a failed purge test — four separate faults
> from one component you can soak in a jug overnight.
>
> **The brew chamber** — remove and wash it. Dishwasher safe; rinse, sanitize, air
> dry [Daily / Weekly / Monthly Maintenance Guide, p3].
>
> #### Descaling — monthly or quarterly?
>
> **The sources disagree, and the disagreement is chronological.**
>
> | Document | Interval | Date |
> |---|---|---|
> | Daily / Weekly / Monthly Maintenance Guide, p4 | **Monthly** — "run descaling cycle at least once every month" | Part 19010043 Rev A, 10 Jan 2017 |
> | Quarterly Descaling Procedure, p1 | **Quarterly** — once every 3 months | Part 20.110005571 Rev B, 7 Mar 2016 |
> | Accessing Programming, p10 | "…every 3 months" | undated training deck |
>
> The procedure itself is word-for-word identical in the two documents; only the
> heading and the interval changed. The monthly instruction is the later revision.
>
> **The recommendation for this wiki: descale monthly.** Three reasons. It is the
> most recent instruction. It is the stricter one, and the failure mode of
> descaling too often is a bottle of citric acid, while the failure mode of
> descaling too rarely is the thermoblock replacement list in
> [No water](#flow). And the service training makes it explicit that an operator
> whose water is out of spec must move from quarterly to **monthly** descaling or
> lose warranty cover on every part in the water system [Service Provider Training
> (Part I), p10] — so monthly is already the floor for a large fraction of
> installations.
>
> #### The descale procedure
>
> [Daily / Weekly / Monthly Maintenance Guide, p4; Quarterly Descaling Procedure,
> p1]
>
> 1. Fit the suction cap and tubing to the descaling bottle and connect the suction
>    tube to the descaling port. **Leave the main water line connected.**
> 2. Insert an empty brew basket and handle. Put a pitcher under the purge valve.
>    Lower the locking lever.
> 3. Wrench icon → **Descaling**, then follow the screen.
> 4. Allow up to **20 minutes**. It requires periodic operator interaction, so do
>    not start it and walk away.
> 5. Empty and wash the handle, basket and pitcher.
> 6. Remove the descaling bottle and dispose of it properly. Press in the retaining
>    ring to release the tubing.
>
> **Then run water through the machine.** The descale valve V13 sticking is a
> documented consequence of not doing this [Troubleshooting - StepByStep App, p71].
> The next boot will tell you: three clicks at start-up means V13 is responding.
>
> The machine reports `C:45 M:2` — "Descale Finished" — when the cycle completes.
> That is not an error; press RESTART [Error Codes, p40].
>
> #### Handling the chemicals
>
> Both products are made by Urnex and both are eye irritants; wear eye protection
> and wash after handling [MSDS - Descaler, p1; MSDS - Cleaning Tablet, p1–p2].
>
> - **Descaler** — citric acid based (under 30%). Causes skin irritation and
>   serious eye irritation. In the eyes: rinse for several minutes, remove contact
>   lenses, keep rinsing, get medical advice if it persists [MSDS - Descaler, p1–p2].
> - **Cleaning tablets** — sodium carbonate, sodium percarbonate (an oxygen
>   bleach, 15–30% of the product), citric acid and surfactants. Causes serious eye
>   irritation [MSDS - Cleaning Tablet, p2].
>
> Use only BKON-recommended products, keep a pitcher under the basket for the whole
> descale, and wash the pitcher thoroughly afterwards [Daily / Weekly / Monthly
> Maintenance Guide, p4].
>
> #### Consumables and part numbers
>
> Cleaning tablets `19007372`, purge valve tool `27801749`, purge valve `19006305`,
> cleaning brush `151044`, drip tray screen `19006722`, coffee filters `18008739`
> (500), all-in-one replacement kit `18010752` [BKON Accessories, p1–p2].

---

## 2.6 `daily` — The daily round

**Who needs it and when.** Whoever opens and closes. Short page, high consequence:
three of the documented "bad beverage" causes are start-up errors, not brewing
errors.

### Draft

> ### The daily round
>
> #### Starting up
>
> [Daily Start-Up & Shut-Down Guide, p1; Operation Manual, p6]
>
> 1. Confirm the water, drain and air lines are connected and the water supply
>    valve is open.
> 2. **Take the brew handle and basket out of the tower.** The machine calibrates
>    during start-up and a locked chamber corrupts it.
> 3. Insert an empty brew handle and basket, leaving the locking handle **up**.
> 4. Turn the power switch on and let the initialization sequence finish before
>    doing anything.
>
> Step 2 is the one that matters. A chamber locked during start-up produces a
> calibration error whose only symptom is consistently poor beverages, with no code
> [Troubleshooting Guide, p2]. If quality drifts and nothing else explains it,
> restart with the tower empty.
>
> The initialization takes about fifteen seconds of water movement and then heats:
> thermoblock 1 to 45 °C, thermoblocks 2 and 3 to 120 °C, and the sequence ends
> when the mix sensor reads 90 °C [AIR and WATER FLOW, p4–p9]. If you want to know
> what all that noise is, see [How the machine works →](#howitworks).
>
> #### Preheating before the first drink
>
> If the machine has been idle, or the brew chamber has been left open, run a rinse
> cycle to preheat the cylinder before brewing [Operation Manual, p8]: insert an
> empty basket and handle, lower the locking handle, put a pitcher underneath,
> press the manual rinse icon, then raise the handle and remove the pitcher. The
> machine has a dedicated internal function for exactly this — "purge with water",
> whose stated purpose is preheating the brew cylinder after an idle period
> [Service Manual, p78].
>
> #### Making a drink
>
> [Operation Manual, p9]
>
> 1. Prepare the purge valve — press the tip of the handle lightly into the valve
>    to clear debris.
> 2. Put the measured product in the brew basket and the basket in the handle.
> 3. Check the basket and handle colours match.
> 4. Insert the handle into the tower.
> 5. Lower the locking handle **fully**, to seal the cylinder.
> 6. Put a cup under the outlet and select the beverage.
>
> #### The colour method
>
> Four coloured handles and baskets ship with every machine. Black, green and
> orange are for tea and other craft beverages; **brown is for coffee**. The point
> is cross-contamination: flavours carry. The touchscreen button colours can be set
> to match, in Craft Cloud, so the screen tells the operator which basket to reach
> for [Operation Manual, p7].
>
> #### Shutting down
>
> [Daily Start-Up & Shut-Down Guide, p1; Operation Manual, p6]
>
> 1. Insert a brew handle with a basket and leave the locking handle **unlocked
>    (up)**.
> 2. Turn the power switch off.
>
> Note the asymmetry: the handle is *out* at power-on and *in* at power-off. It is
> easy to get backwards and it is the difference between a calibrated machine and a
> mystery.
>
> #### Two safety facts that do not change
>
> - Hot water and steam are released repeatedly during cleaning cycles. Keep hands
>   away from the purge valve outlet while the machine is running, and treat the
>   glass cylinder as hot [Operation Manual, p3].
> - Never disconnect the hot water line before the lines have been purged or have
>   cooled. There is a **Cool Down** function in the service menu for exactly this;
>   it finishes when the thermoblocks reach 65 °C [Operation Manual, p3;
>   Accessing Programming, p42].

---

## 2.7 `water` — Water, scale and the warranty

**Who needs it and when.** Before installation, and again the first time anything
scales. This is a short page that explains a disproportionate share of the archive:
the flow-meter failure path, the squeaking nozzle, the leaking overpressure valve
and the thermoblock replacement list are all one root cause.

### Draft

> ### Water, scale and the warranty
>
> More of this machine's documented failures trace back to water chemistry than to
> any other single cause. Franke treats the water specification as a warranty
> condition, not a recommendation.
>
> #### The specification
>
> | Measure | Required | Recommended |
> |---|---|---|
> | Total hardness | < 7 grains/gallon | < 3 grains/gallon |
> | Total dissolved solids | < 200 ppm | 85–115 ppm |
> | pH | 7.0 | 7.0 |
> | Total alkalinity | < 100 ppm | 30–35 ppm |
> | Total chlorine | 0 ppm | — |
> | Calcium / magnesium | — | 30–35 ppm |
> | Sodium–potassium | — | 11 ppm |
> | Iron | 0 ppm | — |
> | Detectable odour | none | — |
> | Input pressure (static and dynamic) | 30–90 psi | 30–90 psi |
> | Input temperature | < 90 °F | < 90 °F |
>
> *Sources: [Pre-Installation Checklist, p3]; [BKON Installation Check List, p6].*
>
> The distinction between the two columns is stated in the source: the **required**
> column is what maintains warranty cover; the **recommended** column is what makes
> the beverage good, "particularly tea".
>
> One more number belongs here: **a unit consumes about 20 ml/s during a recipe**
> [BKON Installation Check List, p6]. A supply that meets the pressure spec at rest
> but cannot deliver that flow will produce a flow-meter error, which is why the
> spec calls out static *and* dynamic pressure.
>
> #### What happens if the water is out of spec
>
> The service training states the options explicitly [Service Provider Training
> (Part I), p10]:
>
> 1. Install filtration that brings TDS into spec, or
> 2. Increase the descale frequency from quarterly to **monthly**, or
> 3. Accept that **the warranty on every part in the water system is void**.
>
> #### What scale actually does to this machine
>
> Reading the fault documents together, scale presents in a recognisable order:
>
> - **Air where water should be.** A leaking overpressure valve leaves air in the
>   line, so a manual rinse becomes ineffective and water takes a long time to
>   arrive. The field notes mark this as urgent and tell you to go looking for
>   further scale damage [Troubleshooting - StepByStep App, p70].
> - **A squeak while filling.** The nozzle has scaled and can no longer return
>   [Troubleshooting - StepByStep App, p70].
> - **A flow-meter error.** The unit is clogged with scale; check flow through the
>   thermoblocks; flush and descale, or replace them [Error Codes, p31, p33].
> - **Then the bill.** If limescale is confirmed in TB2/TB3, the documented repair
>   is both thermoblocks *plus* the air sanitizing valve, the overpressure valve,
>   the fill and rinse valves and the rinser assembly — everything the scaled water
>   passed through [Flow Meter Error, p2].
>
> A water test kit is available from technical support, and the flow-meter document
> instructs a technician to obtain one whenever limescale is found.
>
> #### Filtration
>
> The installation checklist requires that a filtration system be installed and
> that the source feeding the BKON is on it, and that a full water test be
> completed with the kit Franke supplies [Installation Checklist, p1]. The
> pre-installation form must be returned before installation is even scheduled
> [Pre-Installation Checklist, p3]. That is how seriously the vendor takes it.

---

## 2.8 `howitworks` — How the machine works

**Who needs it and when.** Nobody urgently — which is the point. This page exists so
that the diagnostic pages read as consequences rather than as lists. It is the page
that makes "the vacuum pump is downstream of the flow regulator" mean something.

### Draft

> ### How the machine works
>
> The brewer is two boxes. The **tower** on the counter holds the brew chamber, the
> plunger, the atmosphere valve, the pressure sensor and the user interface. The
> **Water Vacuum Supply Center (WVSC)** under the counter holds the water pump, the
> three thermoblocks, the flow meters, the vacuum pump, the air/water separator and
> both circuit boards [Operation Manual, p4; Service Manual, p4].
>
> Between them run eight connections: hot water, cold water and air from the WVSC
> up to the tower; drains from the tower, the WVSC and the tower drain pan down to
> the store drain; a communication cable; and the water supply
> [Installation Manual, p9]. **The tower drain and the WVSC drain must never be
> connected to each other** — that is a documented cause of `C:40 M:5`.
>
> #### RAIN, in one paragraph
>
> Vacuum removes the air trapped in the cellular structure of the leaf or the
> grounds. When the vacuum is released, water rushes into the void it left. That
> changes how infusion happens and how much soluble material comes out, and it
> happens in seconds rather than minutes [BKON Beverage Innovation Capabilities,
> p3; Future of Craft, p5–p6]. Everything else in the machine exists to deliver
> water at an exact temperature and then to control the pressure above it.
>
> #### The valves
>
> Twelve solenoid valves, and their numbers appear in every fault document, so the
> map is worth having:
>
> | | Name | Job |
> |---|---|---|
> | V1 | Mains / water inlet | Water into the unit |
> | V2 | Air sanitizing | Flushes water through the air/water separator |
> | V3 | Fill | Water down into the brew chamber |
> | V4 | Rinse | Water sideways into the brew chamber |
> | V5 | Mixing (proportional) | Blends cold water in to hit the target temperature |
> | V6 | Atmosphere | Lets air out of the brew chamber; energised for vacuum and purge; on top of the tower |
> | V7 | Air leakage | Regulates the vacuum by admitting air |
> | V8 | Blow out | Clears water from the air/water separator |
> | V9 | Flush | Air path to drain — the Service Manual calls this one "purge" |
> | V10 | Vacuum | Air path to the vacuum pump |
> | V11 | Brewing | Hot side to the tower |
> | V13 | Descaling | Only used during descale |
>
> *Sources: [Valves, p1]; [Air_water Flow Diagram, p1]; [Components, p38];
> [Service Manual, p60]; [Service Provider Training (Part I), p111] for V7's role.*
>
> **Naming caution.** The flow diagram and the parts list call V9 "Flush"; the
> Service Manual's water/air legend calls it "Purge" [Air_water Flow Diagram, p1 vs
> Service Manual, p60]. Same valve. The Service Manual's sequence-of-operations
> section uses "purge valve (V9)" throughout, which is also the name of the
> consumable in the portafilter, so read carefully.
>
> Also on the diagram: **FR1** the fill-line flow regulator, **FR2** the vacuum-leak
> flow regulator (the adjustment point for vacuum calibration, on top of the
> tower), **FM** the flow meter, **WS** the water separator, **PS** the pressure
> sensor, **M1** the water pump, **M2** the vacuum pump, **CV** check valves
> [Air_water Flow Diagram, p1; Accessing Programming, p27].
>
> #### Temperatures and pressures
>
> | Component | Setpoint | Cut-out |
> |---|---|---|
> | Thermoblock 1 (cold side) | 45 °C / 113 °F | hi-limit trips at 75 °C / 167 °F |
> | Thermoblocks 2 and 3 (hot side) | 120 °C / 248 °F | hi-limits trip at 150 °C / 302 °F |
> | Mix sensor at end of initialization | 90 °C / 194 °F | — |
> | Cool Down completes at | 65 °C | — |
>
> *Sources: [Components, p9, p11]; [AIR and WATER FLOW, p7–p9]; [Accessing
> Programming, p42].*
>
> Two thermoblocks are used on the hot side rather than one purely to keep up with
> the required flow rate [Service Provider Training (Part I), p75].
>
> Safety valves: **UV1** at 12 bar (174 psi) [Air_water Flow Diagram, p1;
> Service Manual, p60].
>
> **An unresolved conflict about UV2 and UV3.** The flow diagram gives UV2 as an
> overpressure valve at 3 bar (45 psi) and UV3 as an overpressure relief at 3 bar
> (45 psi) [Air_water Flow Diagram, p1], and the components deck agrees that UV3
> opens at 3 bar to keep steam out of the lines [Components, p21]. The Service
> Manual's legend gives UV2 as 2 bar (29 psi) and UV3 as a *dispense* valve at
> 0.2 bar (3 psi) [Service Manual, p60]. The Service Manual's figure is the one
> that matches the documented purge behaviour — the purge valve opens once pressure
> exceeds 3 psi [AIR and WATER FLOW, p15; Service Provider Training (Part I),
> p109] — but the conflict is unresolved and you should measure rather than trust
> either.
>
> #### Start-up, second by second
>
> [AIR and WATER FLOW, p4–p9]
>
> | Window | What is energised | Where the water goes |
> |---|---|---|
> | 0–5 s | V1, V5 | Cold side to drain, on mains pressure alone |
> | 5–10 s | + M1, V11 | Both cold and hot sides to drain |
> | 10–15 s | V5 drops out | Hot side only, to drain |
> | then | TB1 heats to 45 °C, then TB2 and TB3 to 120 °C | — |
> | end | Water through the overpressure valve to drain until the mix sensor reads 90 °C, then everything de-energises | — |
>
> This is the sequence you watch, at the tower's disconnected C and H lines, when
> diagnosing `C:40 M:5`. Knowing it turns a bucket of water into a test.
>
> #### A brew, step by step
>
> [AIR and WATER FLOW, p10–p17; Service Manual, p78–p84]
>
> 1. **Start** — V1, M1 and V11 energise; water goes through the overpressure valve
>    to drain while the machine gets to temperature.
> 2. **Temperature** — the mix sensor watches; V5 modulates cold water in; water
>    still runs to drain.
> 3. **Preparation vacuum** — a small vacuum before any water enters. It does two
>    jobs: it checks for an air leak, and it leaves a pressure buffer so the first
>    water in does not flash to steam and over-pressurise the cylinder
>    [Service Manual, p78]. **This is the first three seconds of every beverage.**
> 4. **Fill** — V3 and V11 open; water goes down into the chamber; displaced air
>    escapes through the atmosphere valve V6.
> 5. **Rinse** — V3 closes, V4 opens; water goes in sideways, washing the walls.
>    When the programmed volume is reached everything upstream de-energises.
> 6. **Vacuum (infusion)** — V6, V10 and the vacuum pump M2 run; the pressure sensor
>    watches; air passes through the air/water separator and out via V9 to drain.
>    The pump modulates its speed to hold the setpoint [Service Manual, p80].
> 7. **Steep** — nothing moves. The atmospheric pause.
> 8. **Purge (dispense)** — V6, V9 and M2 push pressure up. Once it exceeds about
>    3 psi at the purge valve, the check valve inside the purge valve is forced open
>    and the beverage leaves the cylinder [AIR and WATER FLOW, p15;
>    Service Manual, p84].
> 9. **Blow out** — V9, V8 and M2 clear the water out of the air/water separator to
>    drain, after every beverage. Water must be kept out of the vacuum pump
>    [Service Provider Training (Part I), p110].
>
> Steps 4–8 repeat, in whatever order and however many times the recipe specifies.
> A "prewash" is the same machinery used to rinse the leaves before the real fill —
> mostly for darker teas [Service Manual, p84].
>
> There is one more cycle, **Sanitize**, in which V2, V8, V1 and M1 flush water
> through the air/water separator to drain [AIR and WATER FLOW, p17].
>
> #### Why this page matters for the recipe builder
>
> Look at step 6 again. The pump *modulates its speed* against a pressure sensor to
> hold a setpoint. That is why a vacuum step has both a depth and a hold time, and
> why the depth is a real physical target rather than a duty cycle. And look at step
> 8: a purge is the same hardware pushing the other way, which is why the recipe
> format uses the same `ps` key for both. See [Units, ranges and limits →](#reference).
>
> #### Electrics, briefly
>
> 208 V single phase, 20 A maximum, on a 30 A NEMA L6-30P receptacle [Spec Sheet,
> p2]. Inside, a power supply converts 208 VAC to 24 VDC for the boards and the
> solenoids; the water pump motor runs on 208 VAC [Service Training (Part II), p17;
> Flow Meter Error, p1–p2]. Four boards: the high-voltage (secondary) board and the
> low-voltage (command/main) board in the WVSC, and the user interface board and
> the LIM (LED interface module) board in the tower [Service Training (Part II),
> p4, p19–p20]. The comms path is main board X203 → LIM J1 → UI J10
> [LIM Communication Error, p1].
>
> The machine measures 10.75″ × 17″ × 24″ [Spec Sheet, p2].

---

## 2.9 `rain` — Designing a RAIN recipe

**Who needs it and when.** Anyone using the recipe studio who wants their first
attempt to be defensible. This page consolidates the relationships already recorded
in `INTEL.md` and adds the coffee half, which `INTEL.md` only gestures at.

### Draft

> ### Designing a RAIN recipe
>
> A recipe is five elements. Four of them are ordinary brewing variables and one is
> the reason this machine exists.
>
> | Element | Unit | What it is |
> |---|---|---|
> | Water | ml | Enters the chamber two ways: a downward **fill** or a sideward **rinse** |
> | Temperature | °F, delivered to ±1 °F | The water at the moment it enters the chamber |
> | Vacuum | kPa | Depth and duration of the reduced-pressure state |
> | Steep | seconds | Time at normal atmospheric pressure |
> | Purge | kPa | The positive pressure that ends the recipe and separates the solids from the liquid |
>
> *Source: [RAIN Menu Development Guide, p4].*
>
> #### What a base tea recipe looks like
>
> The vendor's worked example, read in order: a 241 ml fill, immediately a 24 kPa
> vacuum, then a 35 ml rinse and a 15-second atmospheric pause. Those steps repeat
> until the purge. A 70 ml rinse stays in the portafilter at the end
> [RAIN Menu Development Guide, p5].
>
> #### The three relationships worth memorising
>
> **1. The vacuum ladder.** In the low- and high-temperature base recipes, if the
> first vacuum is X kPa, the second is X+2 and the third is X+1 [RAIN Menu
> Development Guide, p6–p7].
>
> **2. Hotter starts shallower.** The low-temperature menu's starting point is
> 175 °F at 24 kPa; the high-temperature menu's is 205 °F at 20 kPa. Steep times
> between vacuums also differ between the two [RAIN Menu Development Guide, p6].
> Recipes are programmed across 165–205 °F.
>
> **3. Delicate leaves get one vacuum.** Broken-leaf senchas, gyokuro, first-flush
> darjeelings — these over-extract under a standard ladder. The delicate-leaf base
> recipe uses a single vacuum, a much shorter steep, and puts the great majority of
> the water in at the front of the recipe [RAIN Menu Development Guide, p7].
>
> #### Dialling in: big steps with vacuum, small steps with time
>
> Recipes are named `temperature/vacuum/steep`, where the vacuum and steep figures
> are offsets from the category's zero point. `185/0/0` is the mid-point of the
> 185 °F category; `185/+2/0` is the same recipe two kilopascals deeper
> [RAIN Menu Development Guide, p8].
>
> - **Vacuum changes concentration** and mouthfeel. Move it in steps of **±2 kPa**.
> - **Steep time at the end of the recipe changes flavour intensity.** Move it in
>   steps of **±5 or ±10 seconds**.
>
> Start at the category mid-point and taste. The guide's own summary: big steps with
> the vacuum, little steps with the steep time [RAIN Menu Development Guide, p9].
>
> This project's `advisor.py` was written to move vacuum by 2 and steep by 5 per
> request before this document was read. It matches [INTEL.md].
>
> #### Coffee is a different instrument
>
> Coffee uses the same five elements with different levers, and the differences are
> counter-intuitive enough to be worth stating [RAIN Menu Development Guide,
> p14–p17]:
>
> - **Grind coarser.** Much coarser — expect to sit between the last two settings
>   on the dial. The vacuum strips CO₂ so fast that fine grinds are unnecessary; a
>   coarse grind gives access to the cellular structure without adding surface area.
>   Going to paper filters means about two full numbers coarser again.
> - **Three base temperatures**: 196 °F / 91 °C, 199 °F / 93 °C, 202 °F / 95 °C.
>   Anything from 165–210 °F is available inside a recipe, but the guide's own
>   framework is those three. Darker roast, cooler water.
> - **Do not move the vacuum depth — move its duration.** The base recipes hold one
>   weak vacuum for four seconds. Changing that duration by a single second visibly
>   alters the extraction curve. Depth is deliberately left alone for coffee because
>   its effect on flavour is too large.
> - **Purge pressure is a roast-degree lever.** The zero points are **28 kPa for
>   light, 29 kPa for medium, 31 kPa for dark roasts**, with ±1 available inside a
>   flight. Higher purge pressure means more turbulence and a more aggressive cup.
> - **Steep zero point is 43 seconds**, adjusted in the same ±5 / ±10 second steps
>   as tea.
>
> A dial-in button reads like `196 MR V0 T0 P0`: 196 °F, medium roast, vacuum at its
> zero point (four seconds), steep at its zero point (43 s), purge at its zero point
> (29 kPa) [RAIN Menu Development Guide, p15].
>
> On strength: for most grinders the guide finds a TDS of 1.20–1.30 optimal, and
> notes that because the extraction curve is bent so sharply, a reading that would
> be over-extracted on another method can taste correct here. A very good grinder
> was found to hold up to 1.40 TDS / 20.5% yield without tasting over-extracted, and
> no further [RAIN Menu Development Guide, p16].
>
> #### Filtration medium changes the recipe
>
> The coffee baskets take the laser-etched stainless filter in their base, or paper,
> or other media. Each gives a different cup, and each needs a different grind
> setting [RAIN Menu Development Guide, p15–p16]. The etched filter is described as
> eliminating turbulence during the purge [Future of Craft, p8].
>
> #### How deep can a vacuum go?
>
> The Service Manual's brew-parameter chart works through an example with a vacuum
> of **−40 kPa held for 17 seconds** and a purge of **30 kPa held for 15 seconds**
> [Service Manual, p85–p86]. So the base recipes at 20–24 kPa are using a small
> fraction of the machine's range. The chart also gives the conversion outright:
> 100 kPa = 1 bar = 14.5 psi = 29.5 inHg.
>
> #### Where recipes live
>
> A menu holds 8 categories × 4 pages × 8 buttons — 32 recipes per category, 256 per
> menu. **The first page of a category is the easiest to reach at the machine, so
> the highest-volume drinks belong there** [RAIN Menu Development Guide, p11].
> Compiling a menu produces a `.bbp` file whose name must be eight characters or
> fewer [RAIN Menu Development Guide, p12]. See
> [Menu files and longer recipes →](#menufile).

---

## 2.10 `service-menu` — Service menu: tests, calibrations, logs

**Who needs it and when.** Referenced by every diagnostic page. Currently the wiki
does not mention that the machine has a diagnostic mode at all.

### Draft

> ### Service menu: tests, calibrations, logs
>
> Three menus, reached three ways.
>
> **The wrench icon** — no passcode. Clean in Place, Time/Date, Update Recipe File,
> Descaling, Load and Run Dev Tea, Export to Recipe File [Accessing Programming,
> p3].
>
> **The `i` icon** — UI software version, main board firmware version, menu file
> name, brew cycles, descaling cycles, clean-in-place cycles [Accessing
> Programming, p50]. Photograph this before you do anything else.
>
> **Press and hold the BKON logo for five seconds, then enter 4576** — the
> administration and service screens [Accessing Programming, p14;
> Service Manual, p50].
>
> | Screen | Contains |
> |---|---|
> | Administration (I) | Update MB Firmware · View Log · Export Log · Clear Log · Reset Counters |
> | Service (II) | Field · Neg Pressure Leak Test · Pos Pressure Leak Test · Factory · Cool Down |
> | Field | Vacuum Calibration · Water Calibration · Purge Test |
> | Factory | Vacuum Calibration · Water Calibration · Nitrogen Flush — set at the factory before shipping |
>
> *Source: [Accessing Programming, p16–p41].*
>
> **The layout varies by software version.** The Service Manual shows an older,
> flatter menu with Calibration, Vacuum Calibration, Cool Down and Nitrogen Flush at
> one level [Service Manual, p50]. Follow the screen in front of you.
>
> #### Cool Down — do this first
>
> If the machine is on when you arrive, the water system is full of hot water under
> pressure. Cool Down runs the main valve and the pump while the water drains, and
> completes when the thermoblocks read 65 °C. **Do not remove any hose while the
> unit is hot** [Accessing Programming, p42; Service Manual, p5].
>
> #### The logs
>
> View Log shows the statistics log and the error log; error entries carry a code,
> a date and a time [Accessing Programming, p18–p19]. Export Log writes to a USB
> drive. Clear Log and Reset Counters exist — think before using them, since the
> counters are the maintenance record.
>
> #### Water calibration
>
> Measures the flow rate. The machine reports OK, HIGH or LOW and tells you which
> way to turn the pump bypass screw [Service Manual, p51]:
>
> - **OK** — flow rate between **13.5 and 14.5**
> - **HIGH** — between **14.5 and 15**: open the bypass by turning the screw
>   counter-clockwise
> - **LOW** — close the bypass by turning clockwise
>
> The pump is behind the top and right side panels. Loosen the locking nut, turn the
> adjustment screw in **quarter-turn increments or less**, retighten the nut, and
> re-run the test. The pump runs about 30 seconds per test and you must re-enter the
> passcode each time [Service Manual, p51–p52].
>
> *The unit of "13.5–14.5" is not stated in the source. It is not ml/s — a recipe
> consumes about 20 ml/s [BKON Installation Check List, p6]. Treat it as the
> machine's own index and go by the OK/HIGH/LOW verdict. Inferred, not documented.*
>
> Incoming pressure should be 30–90 psi, checked here as well [Accessing
> Programming, p28].
>
> #### Vacuum calibration
>
> Measures the vacuum the machine can create and reports too low, too high, or good.
> The adjustment is at the **airflow regulator FR2, on top of the tower**
> [Accessing Programming, p26–p27].
>
> Two conditions, both easy to get wrong [Service Manual, p53–p54]:
>
> - **A brew handle and basket must be installed and the locking handle must be
>   down.** The calibration does not work otherwise.
> - Loosen the locking nut, turn the adjusting knob **clockwise to increase**
>   vacuum and counter-clockwise to decrease, a quarter turn at a time, checking
>   after each. Retighten the nut.
>
> #### Purge test
>
> Measures the pressure at which the purge valve opens. See [Chamber not
> sealed →](#sealed) for the full procedure and the range conflict between sources.
> The short version: tape the portafilter hole, run the test, 20–25 is good, low
> means a leak, high means a blockage [Troubleshooting - StepByStep App, p51–p52;
> Accessing Programming, p30].
>
> #### Leak tests
>
> Negative and positive pressure tests, each available for the **Tower** and for the
> **WVSC**. Both report "leak detected" or "no leak detected". A tower result points
> at components in the tower; a WVSC result covers the whole unit [Accessing
> Programming, p32–p37].
>
> #### Software and menu updates
>
> Three separate procedures, and **the machine's power state differs for each**
> [Troubleshooting Guide, p1; Software Download Instructions, p3–p4;
> Accessing Programming, p44–p48; Service Manual, p49]:
>
> | What | Power | Procedure | Time |
> |---|---|---|---|
> | User interface software | **Off** at the start | Insert the drive, power on, select YES, wait, remove the drive, OK, power off 20 s, power on, enter date and time | ~20 s |
> | Main board firmware | **On** | Hold the logo 5 s, enter 4576, insert the drive, Update MB Firmware, select the `.FSW` file, remove the drive, Restart Machine, power off 20 s, power on | up to 6 min |
> | Menu / recipe file | **On** | Insert the drive, wrench icon, Update Recipe File, select the file, OK, remove the drive, power cycle | ~30 s |
>
> **The USB layout is load-bearing.** The software package must be copied onto an
> otherwise-empty thumb drive with its folder structure intact; the upload fails if
> the files are lifted out of their named folder [Software Download Instructions,
> p2]. The distribution zip is fetched from Franke's resource centre; the deck
> prints a shared login, which is not reproduced here.
>
> After a software update, the documented practice is to photograph the `i` screen
> and send it to Franke with the store name and address [Software Download
> Instructions, p4].
>
> #### Export to Recipe File
>
> Copies the unit's current menu out to a USB drive. **Make a backup before working
> on a unit** [Accessing Programming, p13]. For this project it is also the cleanest
> route to a known-good `.bbp` — see [Menu files and longer recipes →](#menufile).
>
> #### Load and Run Dev Tea
>
> A slot for a one-off recipe pushed to a machine for troubleshooting, which does
> not disturb the regular menu. The documentation says it is not initiated by a
> field technician [Accessing Programming, p12] — but it is the machine's own
> equivalent of what this integration does over Bluetooth, and worth knowing exists.

---

## 2.11 `parts` — Parts, and what to have on hand

**Who needs it and when.** Ordering, and deciding whether a fault is worth chasing.
Small page; earns its place because every diagnostic page ends in a part number and
repeating the tables four times would be worse.

### Draft

> ### Parts, and what to have on hand
>
> #### Minimum truck stock
>
> The vendor's own list of what to carry [Required Parts, p1]:
>
> | Part | Description |
> |---|---|
> | `19008816` | Flowmeter valve Ø2.0 mm |
> | `19006201` | Valve, 3/2-way ¼" |
> | `19006226` | Valve, 2/2-way ⅛" |
> | `19006227` | Valve, 3/2-way ⅛" |
> | `19006258` | Gasket, plunger seal profile |
> | `19006265` | Brew chamber silicone ring, 80 shore (×2) |
> | `19006305` | Purge valve for portafilter — long (×4) |
> | `19006337` | Overpressure valve, safety 2.6 bar |
> | `19006421` | Solenoid water valve, 1-way ⅜", 24 V |
> | `19006430` | Pressure switch |
> | `19006431` | Electronic board, low voltage |
> | `19006432` | Electronic board, high/low voltage |
> | `19006590` | Tube, glass brew pipe |
> | `19006725` | LIM / LED board for UI |
>
> *Note: the flowmeter valve is listed as `19008816` here and as `19006173` in the
> flow-meter fault document and the step-by-step app [Flow Meter Error, p3;
> Troubleshooting - StepByStep App, p5]. Confirm before ordering.*
>
> #### Consumables and accessories
>
> [BKON Accessories, p1–p2]
>
> | Part | Description |
> |---|---|
> | `19006258` | Plunger gasket |
> | `19006590` | Brew chamber — glass only |
> | `19006265` | Silicone ring |
> | `18007897` | Brew chamber assembly — glass and rings |
> | `19006722` | Drip tray screen |
> | `20.210001283` | Drip tray cover |
> | `27801749` | Purge valve tool |
> | `19006993` / `19006996` / `19006994` | Brew basket — black / green / orange |
> | `19006802` | Coffee basket |
> | `19006803` | Coffee cap |
> | `19006364` | Brew handle (no colour clip) |
> | `18009328` | Brew handle clips |
> | `19006305` | Purge valve |
> | `19007372` | Cleaning tablets |
> | `18010752` | All-in-one replacement kit |
> | `19006351` | Splash guard |
> | `18008739` | Coffee filters (500) |
> | `151044` | Cleaning brush |
>
> #### Per-fault kits
>
> Each of the dedicated fault documents opens with the same instruction — take the
> parts list with you — and each carries its own [Brew Chamber Glass Error, p1;
> Brew Chamber not Closed Error, p2; Flow Meter Error, p3; LIM Communication Error,
> p1–p2]. The relevant list is at the foot of each fault page in this wiki.
>
> For the LIM communication path specifically: low-voltage main board `19006431`,
> LIM/LED board `19006725`, user interface display `19006362`, 36" base-to-tower
> harness `19006501`, tower-to-LED harness `19006504` [LIM Communication Error, p2].
>
> #### What ships with a machine
>
> Worth knowing when something goes missing: one brew cylinder, four brew handles,
> three each of black, green, orange and brown baskets, four colour clips, five
> purge valves and a purge valve tool, a water line filter-sieve, a cleaning brush,
> 100 coffee filters and filter caps, a drain pan with gasket, filter and cover, a
> communications cable, five Teflon lines, a USB thumb drive, cleaning tablets and a
> descaling bottle with solution [Installation Manual, p5].

---

# 3. Pages I decided *not* to create

Two candidates from the brief that I considered and rejected, plus two of my own:

**A separate installation page.** The archive has five documents on it
(Installation Manual, Pre-Installation Checklist, Installation Checklist, Counter
Layout & Clearance Guidelines, Countertop Cut-Out Template). It is genuinely
detailed — counter clearances, cut-out templates, the eight-connection diagram. But
this project's reader owns an installed machine. The two facts from that corpus
that matter after installation are the water specification and the
drains-must-not-be-joined rule, and both are already placed where they get used
(`water` and `flow`). A page nobody opens is worse than no page.

**A marketing / "what is RAIN" page.** Six documents (Future of Craft, Beverage
Innovation Capabilities, Unlocking Your Culinary Potential, two case studies,
Testimonials, Beverage Cart, four videos) are sales material. Two paragraphs of it
are genuinely useful — the mechanism of vacuum-then-infusion, and the fact that
infused waters and spirits are a supported use — and those belong at the top of
`howitworks` and in `rain` respectively. The rest is not reference material.

**A wiring / electrical page.** The Service Manual has full connector pinouts with
wire colours [Service Manual, p74–p77] and Service Training (Part II) maps every
socket on both boards. This is real, useful content — but it is for someone with
the covers off and a multimeter, which is a different audience from everyone else in
this wiki, and reproducing pin tables adds bulk that only helps at that one moment.
The two facts that generalise (Thot wires green / Tmix wires grey; the comms path
X203 → J1 → J10) are folded into `faults` and `howitworks`. Revisit if the project
ever grows a hardware section.

**A safety page.** The safety warnings are real — hot water and steam, 208 V, the
lifting hazard — but a page of warnings is a page nobody reads. They are placed
inline instead, at the three points where they apply: hot water in `daily` and
`maintenance`, Cool Down before service in `service-menu` and `flow`, and chemical
handling in `maintenance`.

---

# 4. What to cut

Opinionated, as asked.

### `architecture` — dissolve it

It is a diagram and three paragraphs, and every one of those paragraphs already
appears on `overview`, `protocol` or `rag`. The diagram is good and should move to
the top of `overview`, where it does the job it was drawn for: orienting someone in
their first thirty seconds. As a standalone nav entry it is a page that describes
the shape of the software to a reader who wanted to know about the coffee machine.

### `fidelity` — merge into `protocol`

"How faithful is this to the vendor app" is the last section of a protocol
document, not a peer of it. It is also, honestly, a page written for the author
rather than the reader: it is the record of an audit. Keeping it is right; giving
it top-level billing implies a reader who is comparing two implementations, and
there is no such reader.

### `entities` + `services` — merge into one `hass` page

Two tables that are always read together, because the answer to "how do I do X" is
"call this service and watch that sensor". Splitting them makes you navigate
mid-thought.

### `rag` — merge into `concierge`

`concierge` says what asking a question does; `rag` says how to make the answers
better. That is one page with a setup section, not two pages. As it stands, a
reader on `concierge` has no idea `rag` exists unless they scan the whole nav.

### `bbp` + `longer` — merge into `menufile`

These are the same subject approached twice. `longer` asks "can I exceed the
599-byte Bluetooth limit?" and answers "yes, via a menu file"; `bbp` describes that
menu file. Read separately, each ends by pointing at the other. Merged, the page
reads: here is why you would want a menu file, here is what one is, here is what we
can and cannot produce, here is the risk. One caveat for whoever does the merge —
`bbp`'s **Risk** section (a malformed file is flashed to the same address as a good
one) must survive intact and stay prominent. It is the only genuinely dangerous
thing documented anywhere in this project.

### `reference` — split, don't keep whole

The current page bundles units with error codes. Those serve different moments:
units are consulted while writing a recipe, error codes while standing at a broken
machine. The error table moves to `faults` and gets four times bigger; the units
table stays and gets the purge-pressure correction below.

### `overview` — trim, don't cut

It is the landing page and it should stay, but it currently repeats the quickstart,
the architecture and the provenance story. It should be one screen: what this is,
the diagram, and three links.

### Nothing else gets deleted

`quickstart`, `recipes`, `protocol` and the merged pages all still earn their place —
just not above the machine.

---

# 5. Findings that should change the code, not just the wiki

Three things fell out of reading the index that are corrections to this project's
own documentation, not merely new wiki content. They are listed here because they
are the most valuable output of the exercise.

### 5.1 Purge pressure is kilopascals — confirmed

`PROTOCOL.md` lists the purge `ps` unit as unconfirmed, and item 5 of "what still
needs hardware to confirm" is exactly this question. `INTEL.md` records the app's
purge range as 25–35 with the unit unconfirmed.

Two independent documents settle it:

- The Service Manual's brew-parameter chart annotates a purge as "increases pressure
  inside the brew cylinder to **30 kPa** for 15 seconds", alongside a vacuum
  annotated as −40 kPa for 17 seconds, and gives the kPa conversions
  [Service Manual, p85–p86].
- The RAIN guide's coffee section gives purge-pressure zero points of **28 kPa**
  (light roast), **29 kPa** (medium) and **31 kPa** (dark) [RAIN Menu Development
  Guide, p15].

Those numbers sit exactly inside the app's own 25–35 validation window, from two
sources that have never seen the app. `ps` is kPa on both step types; the sign
differs, not the unit. **`PROTOCOL.md` item 5 can be struck.**

### 5.2 `C:2 M:5` is missing from the error table

"Brew Handle not detected". Documented in the service training error table
[Service Provider Training (Part I), p54] and described without its code in two
other places [Service Manual, p56; Troubleshooting Guide, p2]. It is absent from the
Error Codes reference and from this project's table in `PROTOCOL.md`. It should be
added to the integration's lookup.

### 5.3 The temperature-sensor bank is twelve distinct codes

`PROTOCOL.md` collapses `C:11–22 M:5` to "Temperature sensor fault (various
sensors)". The Service Manual gives all twelve individually, each naming a sensor, a
failure mode and a cabinet [Service Manual, p58] — reproduced in §2.1 above. The
integration can report "Thermoblock 2 sensor open (WVSC)" instead of "temperature
sensor fault", which is the difference between a message and an instruction.

Two smaller items in the same vein: the Service Manual and the Error Codes deck
disagree about which code is the mix-water sensor (§2.1), and the archive contains
one more brew-parameter fact worth recording — vacuums of −40 kPa are documented,
so the app's 0–60 kPa validation window is not conservative.

---

# Source key

Documents cited above, as named in `bkon_brewer_kb.json`:

*AIR and WATER FLOW · Accessing Programming · Air_water Flow Diagram ·
BKON Accessories · BKON Beverage Innovation Capabilites · BKON Installation Check
List · Brew Chamber Glass Error · Brew Chamber not Closed Error · Components ·
Daily _ Weekly _ Monthly Maintenance Guide · Daily Start-Up & Shut-Down Guide ·
Error Codes · Flow Meter Error · Future of Craft · Installation Manual ·
LIM Communication Error · MSDS - Cleaning Tablet · MSDS - Descaler ·
No Problem Found · Operation Manual · Pre-Installation Checklist ·
Quarterly Descaling Procedure · RAIN Menu Development Guide · Required Parts ·
Service Manual · Service Provider Training (Part I) · Service Training ( Part II) ·
Software Download Instructions · Spec Sheet · Troubleshooting - StepByStep App ·
Troubleshooting Guide · Vacuum Leak · Valves*

Project documents cited: `INTEL.md`, `PROTOCOL.md`, `BBP_FORMAT.md`,
`LONGER_RECIPES.md`.

No vendor document text is reproduced at length here; every fact above is restated
in this document's own words, with a citation so it can be verified against the
local index.

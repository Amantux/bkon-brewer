"""Natural language to a recipe, with explicit targets honoured.

`templates.suggest` picks a starting shape from a keyword; this goes further. It
reads what the sentence actually asks for -- a beverage, a size, a strength, and
any hard numbers ("205 F", "250 ml", "two vacuums", "8 second steep") -- builds
the steps to hit them, and says what it did and what it could not do.

Everything here is grounded in facts recorded in docs/INTEL.md:

  * base tea recipes start 175 F / 24 kPa (low) and 205 F / 20 kPa (high), so a
    hotter brew starts from a SHALLOWER vacuum, not a deeper one;
  * in a multi-vacuum sequence, if the first is X kPa the next is about X+2 and
    the third about X+1;
  * delicate leaf uses ONE vacuum, a short steep, and front-loaded water;
  * vacuum moves concentration in steps of ~2 kPa, steep moves intensity in
    steps of ~5 s;
  * the vendor app accepts temperature 140-212 F, vacuum 0-60 kPa, purge 25-35,
    fill/rinse 0-600 ml, all times 0-180 s.

Pure: text in, steps out. No Home Assistant, no model, no network -- so the same
compiler serves the `build_recipe` service, the chat tool and the studio, and is
tested directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .protocol import recipe as R

# The app's validated envelope. Anything asked for outside it is clamped and
# reported, never silently accepted.
TEMP_MIN, TEMP_MAX = 140, 212
VAC_MIN, VAC_MAX = 1, 60
PURGE_MIN, PURGE_MAX = 25, 35
FILL_MAX = 600
TIME_MAX = 180

#: Sizes, as the machine's own menus use them.
SIZES = {"small": 250, "medium": 350, "large": 470}

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "a": 1, "an": 1, "single": 1, "double": 2, "triple": 3}


@dataclass(slots=True)
class Target:
    """One thing the sentence asked for, and whether it was honoured."""

    what: str
    value: str
    honoured: bool = True
    note: str = ""


@dataclass(slots=True)
class Compiled:
    steps: list[R.Step]
    style: str                                    # the shape it chose
    targets: list[Target] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.targets:
            return f"Built a {self.style} recipe."
        got = [f"{t.what} {t.value}" for t in self.targets if t.honoured]
        out = f"Built a {self.style} recipe"
        if got:
            out += " targeting " + ", ".join(got)
        out += "."
        if self.unmet:
            out += " Could not: " + "; ".join(self.unmet)
        return out


# -- reading the sentence -----------------------------------------------------

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def parse_temperature(text: str) -> float | None:
    """A temperature in either scale. Celsius is converted, as the app does."""
    m = re.search(r"(\d{2,3})\s*°?\s*(?:deg(?:rees)?\s*)?([fc])\b", text, re.I)
    if m:
        value, scale = float(m.group(1)), m.group(2).lower()
        return value * 9 / 5 + 32 if scale == "c" else value
    # A bare number near the word temperature, e.g. "at 185".
    m = re.search(r"\b(?:at|to)\s+(1[4-9]\d|2[01]\d)\b", text)
    return float(m.group(1)) if m else None


def parse_volume(text: str) -> int | None:
    m = re.search(r"(\d{2,3})\s*(?:ml|millilit)", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,2})\s*(?:oz|ounce)", text, re.I)
    return int(round(int(m.group(1)) * 29.57)) if m else None


def parse_vacuum(text: str) -> int | None:
    m = re.search(r"(\d{1,2})\s*kpa", text, re.I)
    return int(m.group(1)) if m else None


def parse_steep(text: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*(?:s|sec|secs|second|seconds)\b[^.]{0,18}steep", text, re.I)
    if not m:
        m = re.search(r"steep[^.]{0,18}?(\d{1,3})\s*(?:s|sec|secs|second|seconds)\b", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,2})\s*(?:min|minute)", text, re.I)
    return int(m.group(1)) * 60 if m else None


def parse_vacuum_count(text: str) -> int | None:
    m = re.search(r"\b(\d|one|two|three|four|five|single|double|triple)\s+vacuum", text, re.I)
    if not m:
        return None
    tok = m.group(1).lower()
    return int(tok) if tok.isdigit() else _NUMBER_WORDS.get(tok)


def parse_size(text: str) -> str | None:
    low = text.lower()
    for word, size in (("small", "small"), ("little", "small"), ("short", "small"),
                       ("large", "large"), ("big", "large"), ("tall", "large"),
                       ("medium", "medium"), ("regular", "medium")):
        if re.search(rf"\b{word}\b", low):
            return size
    return None


#: Beverage styles, each a starting point grounded in the published base recipes.
STYLES: dict[str, dict] = {
    "delicate tea": {
        "match": r"delicate|sencha|gyokuro|darjeeling|first flush|white tea|silver needle",
        "temp": 175, "vacuum": 20, "steep": 3, "vacuums": 1, "front_loaded": True},
    "green tea": {
        "match": r"green tea|jasmine|dragonwell|matcha|gunpowder",
        "temp": 175, "vacuum": 24, "steep": 6, "vacuums": 2},
    "black tea": {
        "match": r"black tea|assam|earl grey|breakfast|ceylon|pu-?erh",
        "temp": 205, "vacuum": 20, "steep": 8, "vacuums": 3},
    "oolong": {
        "match": r"oolong|tieguanyin",
        "temp": 195, "vacuum": 22, "steep": 7, "vacuums": 2},
    "herbal": {
        "match": r"herbal|tisane|chamomile|rooibos|peppermint|hibiscus",
        "temp": 205, "vacuum": 24, "steep": 10, "vacuums": 2},
    "cold brew style": {
        "match": r"cold brew|iced|chilled|over ice",
        "temp": 150, "vacuum": 28, "steep": 12, "vacuums": 3},
    "coffee": {
        "match": r"coffee|espresso|pour ?over|dark roast|light roast|medium roast",
        "temp": 200, "vacuum": 24, "steep": 6, "vacuums": 2},
}
DEFAULT_STYLE = "coffee"

#: Qualitative words, and the direction they push. Grounded in the guide: vacuum
#: is concentration, steep is intensity.
_STRENGTH = {
    r"\b(strong|stronger|bold|robust|intense|punchy|rich|concentrated)\b": +2,
    r"\b(weak|weaker|light|lighter|mild|delicate|subtle|gentle)\b": -2,
}
_INTENSITY = {
    r"\b(bitter|harsh|sharp|astringent)\b": -5,          # asked to avoid -> shorter
    r"\b(smooth|sweet|mellow|rounded|balanced)\b": -5,
    r"\b(full[- ]?bodied|full body|heavy|syrupy)\b": +5,
}


def detect_style(text: str) -> str:
    low = text.lower()
    for name, spec in STYLES.items():
        if re.search(spec["match"], low):
            return name
    return DEFAULT_STYLE


# -- building -----------------------------------------------------------------

def compile_recipe(text: str) -> Compiled:
    """Turn a description into steps, honouring any explicit targets.

    The shape comes from the beverage; the numbers come from the sentence where
    it gives them and from the published base recipes where it does not.
    """
    text = (text or "").strip()
    style = detect_style(text)
    spec = STYLES[style]
    targets: list[Target] = []
    unmet: list[str] = []

    # --- temperature ---
    temp = spec["temp"]
    asked_temp = parse_temperature(text)
    if asked_temp is not None:
        clamped = _clamp(asked_temp, TEMP_MIN, TEMP_MAX)
        honoured = abs(clamped - asked_temp) < 0.5
        temp = clamped
        targets.append(Target("temperature", f"{round(clamped)} °F", honoured,
                              "" if honoured else f"{round(asked_temp)} °F is outside "
                                                  f"{TEMP_MIN}–{TEMP_MAX} °F"))
        if not honoured:
            unmet.append(f"{round(asked_temp)} °F is outside the machine's "
                         f"{TEMP_MIN}–{TEMP_MAX} °F range")

    # --- size / volume ---
    size = parse_size(text)
    volume = parse_volume(text)
    if volume is not None:
        clamped = int(_clamp(volume, 20, FILL_MAX))
        honoured = clamped == volume
        targets.append(Target("volume", f"{clamped} ml", honoured))
        if not honoured:
            unmet.append(f"{volume} ml is over the {FILL_MAX} ml the app allows")
        volume = clamped
    else:
        volume = SIZES.get(size or "medium", SIZES["medium"])
        if size:
            targets.append(Target("size", f"{size} ({volume} ml)"))

    # --- strength: the vacuum, per the guide ---
    vacuum = spec["vacuum"]
    for pattern, delta in _STRENGTH.items():
        if re.search(pattern, text, re.I):
            vacuum += delta
            targets.append(Target("strength",
                                  "stronger" if delta > 0 else "lighter"))
            break
    asked_vac = parse_vacuum(text)
    if asked_vac is not None:
        clamped = int(_clamp(asked_vac, VAC_MIN, VAC_MAX))
        honoured = clamped == asked_vac
        vacuum = clamped
        targets.append(Target("vacuum", f"{clamped} kPa", honoured))
        if not honoured:
            unmet.append(f"{asked_vac} kPa is outside {VAC_MIN}–{VAC_MAX} kPa")
    vacuum = int(_clamp(vacuum, VAC_MIN, VAC_MAX))

    # --- steep: intensity ---
    steep = spec["steep"]
    for pattern, delta in _INTENSITY.items():
        if re.search(pattern, text, re.I):
            steep = max(1, steep + delta)
            break
    asked_steep = parse_steep(text)
    if asked_steep is not None:
        clamped = int(_clamp(asked_steep, 1, TIME_MAX))
        honoured = clamped == asked_steep
        steep = clamped
        targets.append(Target("steep", f"{clamped} s", honoured))
        if not honoured:
            unmet.append(f"a {asked_steep}s steep is over the {TIME_MAX}s limit")

    # --- how many vacuums ---
    count = parse_vacuum_count(text) or spec["vacuums"]
    count = int(_clamp(count, 1, 5))
    if parse_vacuum_count(text):
        targets.append(Target("vacuums", str(count)))

    steps = _assemble(temp, volume, vacuum, steep, count,
                      front_loaded=spec.get("front_loaded", False))
    return Compiled(steps=steps, style=style, targets=targets, unmet=unmet)


def _assemble(temp: float, volume: int, vacuum: int, steep: int, count: int,
              *, front_loaded: bool) -> list[R.Step]:
    """Lay out the steps, following the published vacuum relationship.

    If the first vacuum is X, the next is about X+2 and the third about X+1 --
    so a sequence is built from that pattern rather than repeating one value.
    """
    offsets = [0, 2, 1, 2, 1][:count]
    # Front-loaded (delicate) puts most of the water in first; otherwise the
    # fill is split so later rinses carry extraction through the sequence.
    first_fill = int(volume * (0.85 if front_loaded or count == 1 else 0.7))
    rinse = int(_clamp((volume - first_fill) / max(1, count - 1) if count > 1 else 0,
                       0, FILL_MAX))

    steps: list[R.Step] = [R.start(round(temp)),
                           R.fill(first_fill, rinse_volume_ml=0)]
    for i, off in enumerate(offsets):
        ps = int(_clamp(vacuum + off, VAC_MIN, VAC_MAX))
        steps.append(R.vacuum(ps, steep if i == len(offsets) - 1 else max(1, steep - 2)))
        if i < len(offsets) - 1 and rinse:
            steps.append(R.fill(0, rinse_volume_ml=rinse, pause_seconds=steep))
    steps.append(R.purge(30, 10, detect=True))
    return steps

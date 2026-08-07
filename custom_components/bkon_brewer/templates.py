"""Recipe templates and guided assembly. Pure; see docs/INTEL.md for the values.

Building a recipe from scratch means knowing that a Mac Studio of a machine
wants a Start, a Fill, a Vacuum or two and a Purge, in roughly sensible amounts.
Most people do not, so this offers starting points that already work and a way
to assemble one from a short description, which the concierge and the recipe
builder both use.

The numbers are grounded: temperatures, fills and vacuum strengths come from the
ranges BKON/Franke's RAIN guide states, not from taste. They are a defensible
place to start, not a claim about the best cup -- the advisor is how you tune
from here.
"""
from __future__ import annotations

from dataclasses import dataclass

from .protocol import recipe as R


@dataclass(slots=True)
class Template:
    key: str
    name: str
    description: str
    build: object                       # () -> list[R.Step]


def _pour_over() -> list[R.Step]:
    """A balanced everyday recipe: fill, a short vacuum, a light purge."""
    return [
        R.start(200),
        R.fill(250, rinse_volume_ml=30, pause_seconds=10),
        R.vacuum(24, 4),
        R.purge(50, 10, detect=True),
    ]


def _strong() -> list[R.Step]:
    """More extraction: hotter, a deeper and a second vacuum, a longer steep."""
    return [
        R.start(205),
        R.fill(250, rinse_volume_ml=30, pause_seconds=15),
        R.vacuum(26, 6),
        R.vacuum(28, 5),
        R.purge(50, 10, detect=True),
    ]


def _delicate() -> list[R.Step]:
    """Gentle: lower temperature, one shallow short vacuum. Good for tea."""
    return [
        R.start(175),
        R.fill(250, rinse_volume_ml=20, pause_seconds=10),
        R.vacuum(20, 3),
        R.purge(40, 8),
    ]


def _large() -> list[R.Step]:
    """A bigger cup: more water, the balanced extraction scaled up a touch."""
    return [
        R.start(200),
        R.fill(320, rinse_volume_ml=40, pause_seconds=12),
        R.vacuum(24, 5),
        R.purge(50, 10, detect=True),
    ]


TEMPLATES: dict[str, Template] = {
    t.key: t for t in (
        Template("pour_over", "Balanced Pour Over",
                 "An even, everyday cup — a good starting point.", _pour_over),
        Template("strong", "Strong & Bold",
                 "Hotter, deeper vacuums, longer steep for more intensity.",
                 _strong),
        Template("delicate", "Delicate / Tea",
                 "Lower temperature and a gentle vacuum for teas and light "
                 "roasts.", _delicate),
        Template("large", "Large Cup",
                 "More water for a bigger serving, balanced extraction.",
                 _large),
    )
}


def list_templates() -> list[dict]:
    return [{"key": t.key, "name": t.name, "description": t.description}
            for t in TEMPLATES.values()]


def from_template(key: str) -> list[R.Step] | None:
    t = TEMPLATES.get(key)
    return t.build() if t else None


# -- guided assembly from a short description --------------------------------

# Words that nudge the starting template. Checked in order; the first match
# picks the base, then the advisor's own vocabulary can tune it further.
_HINTS = (
    (("strong", "bold", "intense", "espresso", "rich"), "strong"),
    (("tea", "delicate", "gentle", "light", "green", "herbal"), "delicate"),
    (("large", "big", "mug", "travel"), "large"),
)


def suggest(description: str) -> tuple[str, list[R.Step]]:
    """Pick a starting template from a plain description.

    Returns (template_key, steps). Falls back to the balanced pour-over, which
    is the right default: a sensible cup nobody has to think about, and the
    advisor tunes from there. The description is intentionally NOT parsed into
    fine parameters -- a template plus feedback is easier to reason about than a
    one-shot guess at every value.
    """
    low = (description or "").lower()
    for words, key in _HINTS:
        if any(w in low for w in words):
            return key, from_template(key)
    return "pour_over", from_template("pour_over")

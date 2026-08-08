#!/usr/bin/env python3
"""Per-recipe rating and notes — the user-feedback store.

    python3 tests/test_library_feedback.py

The library needs Home Assistant only for its Store; the feedback logic is plain
dict work. This drives a RecipeLibrary built without HA (a fake in-memory store),
so async_rate / async_put / export round-tripping are all exercised directly.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer.library import RecipeLibrary   # noqa: E402

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")
def ok(n, c): check(n, bool(c), True)
def run(c): return asyncio.get_event_loop().run_until_complete(c)


class FakeStore:
    def __init__(self): self.saved = None
    async def async_save(self, data): self.saved = data


def fresh():
    """A RecipeLibrary with no Home Assistant behind it."""
    lib = RecipeLibrary.__new__(RecipeLibrary)
    lib._store = FakeStore()
    lib._recipes = {}
    lib._loaded = True
    return lib


STEPS = [{"type": "start", "values": {"tmp": 200}},
         {"type": "vc", "values": {"ps": 24, "tm": 6}}]

print("rating and notes attach to a recipe without touching its steps")
lib = fresh()
run(lib.async_put("Morning Cup", STEPS))
ok("rate an existing recipe", run(lib.async_rate("Morning Cup", rating=4, notes="bright, a bit thin")))
rec = lib.get_record("Morning Cup")
check("rating stored", rec["rating"], 4)
check("notes stored", rec["notes"], "bright, a bit thin")
check("steps untouched", rec["steps"], STEPS)
check("rating shows in the listing", lib.list()[0]["rating"], 4)

print("\nrating an unknown recipe is a clean no-op")
check("returns False", run(lib.async_rate("ghost", rating=5)), False)

print("\nout-of-range ratings are clamped; 0 clears; None leaves alone")
run(lib.async_rate("Morning Cup", rating=9))
check("clamped to 5", lib.get_record("Morning Cup")["rating"], 5)
run(lib.async_rate("Morning Cup", notes="changed only the note"))
check("None rating left the rating alone", lib.get_record("Morning Cup")["rating"], 5)
check("note updated on its own", lib.get_record("Morning Cup")["notes"], "changed only the note")
run(lib.async_rate("Morning Cup", rating=0))
check("0 clears the rating", lib.get_record("Morning Cup")["rating"], None)

print("\nfeedback survives an edit, and rides save_recipe's optional args")
lib = fresh()
run(lib.async_put("Cup", STEPS))
run(lib.async_rate("Cup", rating=5, notes="keep this one"))
# re-saving the steps (an edit) must not wipe the rating
run(lib.async_put("Cup", STEPS + [{"type": "pg", "values": {"ps": 30, "tm": 10}}]))
check("rating survives a re-save", lib.get_record("Cup")["rating"], 5)
check("notes survive a re-save", lib.get_record("Cup")["notes"], "keep this one")

print("\nexport prunes empty feedback but round-trips real feedback")
lib = fresh()
run(lib.async_put("Plain", STEPS))
run(lib.async_put("Rated", STEPS))
run(lib.async_rate("Rated", rating=3, notes="ok"))
dump = lib.export_dict()
by = {r["name"]: r for r in dump["recipes"]}
ok("an unrated recipe carries no rating key", "rating" not in by["Plain"])
ok("an unrated recipe carries no notes key", "notes" not in by["Plain"])
check("a rated recipe keeps its rating", by["Rated"]["rating"], 3)

lib2 = fresh()
run(lib2.async_import_records(dump["recipes"]))
check("rating imports back", lib2.get_record("Rated")["rating"], 3)
check("notes import back", lib2.get_record("Rated")["notes"], "ok")
check("the unrated one imports with no rating", lib2.get_record("Plain")["rating"], None)

print("\nthe tasting journal — the part MCP reads")
lib = fresh()
run(lib.async_put("Cup", STEPS))
e = run(lib.async_note("Cup", changes=["vacuum 24kPa -> 28kPa"],
                       taste="fuller body", rating=5, when="2026-08-08"))
ok("an entry comes back", e and e["taste"] == "fuller body")
rec = lib.get_record("Cup")
check("the journal is on the record", len(rec["journal"]), 1)
check("the change is recorded", rec["journal"][0]["changes"], ["vacuum 24kPa -> 28kPa"])
check("the rating rides along", rec["journal"][0]["rating"], 5)

# the library sensor's attributes are the MCP-visible surface
listing = lib.list()[0]
ok("list() exposes the journal (the sensor attribute)", "journal" in listing)
check("and it carries the entry", len(listing["journal"]), 1)

check("noting an unknown recipe is a clean None", run(lib.async_note("ghost", taste="x")), None)

print("\nthe journal is bounded, survives edits, and round-trips")
for i in range(30):
    run(lib.async_note("Cup", changes=[f"c{i}"], taste=f"t{i}"))
check("capped so the sensor attribute cannot bloat",
      len(lib.get_record("Cup")["journal"]), 20)
check("the newest entry is kept", lib.get_record("Cup")["journal"][-1]["taste"], "t29")

run(lib.async_put("Cup", STEPS + [{"type": "pg", "values": {"ps": 30, "tm": 10}}]))
check("journal survives a re-save", len(lib.get_record("Cup")["journal"]), 20)

dump = lib.export_dict()
lib2 = fresh(); run(lib2.async_import_records(dump["recipes"]))
check("journal round-trips through export/import",
      len(lib2.get_record("Cup")["journal"]), 20)
lib3 = fresh(); run(lib3.async_put("Plain", STEPS))
ok("a recipe with no journal exports without the key",
   "journal" not in lib3.export_dict()["recipes"][0])

print("\nbrew history — that it happened, not just what you meant")
lib = fresh()
run(lib.async_put("Cup", STEPS))
run(lib.async_brewed("Cup", when="2026-08-08T09:00:00"))
run(lib.async_brewed("Cup", when="2026-08-08T17:30:00"))
rec = lib.get_record("Cup")
check("both brews recorded", len(rec["brews"]), 2)
check("the counter tracks them", rec["brew_count"], 2)
check("the listing shows the count", lib.list()[0]["brew_count"], 2)
check("and when it last ran", lib.list()[0]["last_brewed"], "2026-08-08T17:30:00")
check("brewing an unknown recipe is a clean no-op",
      run(lib.async_brewed("ghost", when="x")), None)

# history belongs to the recipe's life, not to one version of its steps
run(lib.async_put("Cup", STEPS + [{"type": "pg", "values": {"ps": 30, "tm": 10}}]))
check("history survives an edit", lib.get_record("Cup")["brew_count"], 2)

for i in range(30):
    run(lib.async_brewed("Cup", when=f"2026-09-{i+1:02d}"))
check("the list is bounded", len(lib.get_record("Cup")["brews"]), 20)
check("but the total count is not lost", lib.get_record("Cup")["brew_count"], 32)

lib2 = fresh()
run(lib2.async_put("Never", STEPS))
ok("a never-brewed recipe exports without brew keys",
   "brews" not in lib2.export_dict()["recipes"][0])

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

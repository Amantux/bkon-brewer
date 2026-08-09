#!/usr/bin/env python3
"""Where the drag indicator says a step will land, versus where it lands.

    python3 tests/test_drag_geometry.py

The studio's drag shows a dashed space for the landing slot. If that space is
not exactly where the card ends up, the reorder looks wrong even when the
resulting recipe is right — which is what happened when the indicator was a flow
element: moving it re-laid-out the list on top of the transforms and displaced
everything twice, worst when dragging to the top.

This mirrors the arithmetic in index.html (`shiftOthers`) against a from-scratch
relayout, for every from/to pair, with cards of differing heights — a uniform
list would hide an error the moment a taller Dialog card is in the way.
"""
import sys

GAP = 9                                   # the flex gap between step cards
HEIGHTS = [60, 60, 120, 60, 88]           # a tall Dialog card among short ones

_pass = _fail = 0
def check(n, g, w):
    global _pass, _fail
    if g == w: _pass += 1; print(f"  ok   {n}")
    else: _fail += 1; print(f"  FAIL {n}: got {g!r}, want {w!r}")


def rects(heights):
    out, y = [], 0
    for h in heights:
        out.append({"top": y, "bottom": y + h, "height": h})
        y += h + GAP
    return out


def indicator_top(heights, frm, to):
    """The formula the UI uses to place the dashed landing space."""
    r = rects(heights)
    h = heights[frm]
    return r[to]["top"] if to <= frm else r[to]["bottom"] - h


def actual_top(heights, frm, to):
    """Where the card really ends up, by laying the list out again."""
    order = list(range(len(heights)))
    moved = order.pop(frm)
    order.insert(to, moved)
    y = 0
    for idx in order:
        if idx == frm:
            return y
        y += heights[idx] + GAP
    raise AssertionError("the moved card vanished")


print("the indicator lands exactly where the card lands")
mismatches = []
for frm in range(len(HEIGHTS)):
    for to in range(len(HEIGHTS)):
        a, b = indicator_top(HEIGHTS, frm, to), actual_top(HEIGHTS, frm, to)
        if a != b:
            mismatches.append(f"{frm}->{to}: indicator {a}, actual {b}")
check("every from/to pair agrees", mismatches, [])

print("\nthe cases that were visibly wrong")
for frm in range(1, len(HEIGHTS)):
    check(f"dragging {frm} to the top lands at 0",
          indicator_top(HEIGHTS, frm, 0), 0)
check("dragging the top card down past the tall one",
      indicator_top(HEIGHTS, 0, 2), actual_top(HEIGHTS, 0, 2))
check("dragging to the very bottom",
      indicator_top(HEIGHTS, 0, 4), actual_top(HEIGHTS, 0, 4))
check("dropping on itself does not move",
      indicator_top(HEIGHTS, 2, 2), rects(HEIGHTS)[2]["top"])

print("\nit holds for a uniform list too")
uni = [60] * 5
check("uniform heights agree",
      [indicator_top(uni, f, t) for f in range(5) for t in range(5)],
      [actual_top(uni, f, t) for f in range(5) for t in range(5)])

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

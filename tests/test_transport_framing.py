#!/usr/bin/env python3
"""Message reassembly across BLE notifications.

    python3 tests/test_transport_framing.py

_split_messages is the one pure function in the transport, and it guards the
most annoying class of BLE bug: a logical message split across two
notifications. Getting it wrong truncates the tail of a long dialog, which then
looks like the brewer sent a shorter prompt than it did.

Imported directly from the module without triggering its bleak/HA imports,
which live inside async_connect rather than at module top level precisely so
this stays runnable with no dependencies.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer.transport import _split_messages   # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  ok   {name}")
    else:
        _fail += 1
        print(f"  FAIL {name}: got {got!r}, want {want!r}")


print("newline-delimited")
check("two complete lines", _split_messages("a\nb\n"), (["a", "b"], ""))
check("trailing partial is held back",
      _split_messages("stepCompleted\ndial"), (["stepCompleted"], "dial"))
check("blank lines dropped", _split_messages("a\n\nb\n"), (["a", "b"], ""))

print("\nframe-delimited {msg:...}")
check("single frame",
      _split_messages("{msg:1:<ABORT></ABORT>}"),
      (["{msg:1:<ABORT></ABORT>}"], ""))
check("two frames back to back",
      _split_messages("{msg:1:<A></A>}{msg:1:<B></B>}"),
      (["{msg:1:<A></A>}", "{msg:1:<B></B>}"], ""))
check("incomplete frame is buffered whole",
      _split_messages("{msg:1:<A><"),
      ([], "{msg:1:<A><"))
check("one complete then one partial",
      _split_messages("{msg:1:<A></A>}{msg:1:<B"),
      (["{msg:1:<A></A>}"], "{msg:1:<B"))

print("\nnested braces do not close the frame early")
# The framing is {msg:N:PAYLOAD}; if a payload ever contained braces, a naive
# split on the first '}' would truncate it. Depth-tracking prevents that.
check("nested content stays in one frame",
      _split_messages("{msg:1:{inner}}"),
      (["{msg:1:{inner}}"], ""))

print("\nempty and junk")
check("empty", _split_messages(""), ([], ""))
check("bare text with no delimiter is all leftover",
      _split_messages("no delimiters here"), ([], "no delimiters here"))

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

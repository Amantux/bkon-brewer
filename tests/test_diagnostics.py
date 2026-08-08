#!/usr/bin/env python3
"""Recipe linting and problem diagnosis.

    python3 tests/test_diagnostics.py

Catches trouble before a brew: the linter must flag what will actually go wrong
(no water, too large to send, a blank dialog) without crying wolf on a sound
recipe. Diagnosis must turn a code or symptom into a real next step.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap                          # noqa: E402
_bootstrap.install()

from bkon_brewer import diagnostics as D   # noqa: E402
from bkon_brewer.diagnostics import Severity  # noqa: E402
from bkon_brewer.protocol import recipe as R  # noqa: E402

_pass = _fail = 0


def check(name, got, want):
    global _pass, _fail
    if got == want:
        _pass += 1; print(f"  ok   {name}")
    else:
        _fail += 1; print(f"  FAIL {name}: got {got!r}, want {want!r}")


def sev(findings, s):
    return [f for f in findings if f.severity == s]


print("a sound recipe lints clean of errors")
good = [R.start(200), R.fill(250, rinse_volume_ml=30), R.vacuum(24, 4), R.purge(50, 10)]
f = D.lint_recipe(good)
check("no errors on a good recipe", sev(f, Severity.ERROR), [])

print("\nthe things that will actually break a brew")
check("empty recipe is an error", D.lint_recipe([])[0].severity, Severity.ERROR)
f = D.lint_recipe([R.start(200), R.vacuum(24, 4)])
check("no fill -> error", any("no water" in x.message.lower() or "no fill" in x.message.lower()
                              for x in sev(f, Severity.ERROR)), True)
f = D.lint_recipe([R.start(200), R.fill(250), R.dialog("")])
check("blank dialog -> error", any("blank" in x.message.lower() or "no text" in x.message.lower()
                                   for x in sev(f, Severity.ERROR)), True)

print("\ntoo large to transmit is caught before brewing")
big = [R.dialog("x" * 40) for _ in range(20)] + [R.fill(250)]
f = D.lint_recipe(big)
check("oversized -> error", any("too large" in x.message.lower() for x in f), True)
check("and the fix says what to do", any("combine" in x.fix.lower() for x in f), True)

print("\nout-of-range values are warned, not silently accepted")
f = D.lint_recipe([R.start(250), R.fill(250)])
check("temp above range -> warning",
      any("outside" in x.message.lower() for x in sev(f, Severity.WARNING)), True)
f = D.lint_recipe([R.start(200), R.fill(250), R.vacuum(150, 4)])
check("vacuum over the editor cap -> warning",
      any("vacuum" in x.message.lower() and "60" in x.message for x in sev(f, Severity.WARNING)), True)
# the purge band and fill ceiling, both read from the app's editors
f = D.lint_recipe([R.start(200), R.fill(250), R.purge(50, 10)])
check("purge pressure out of 25-35 -> warning",
      any("purge pressure" in x.message.lower() for x in sev(f, Severity.WARNING)), True)
f = D.lint_recipe([R.start(200), R.purge(30, 10)])
check("a purge at 30 is accepted",
      not any("purge pressure" in x.message.lower() for x in sev(f, Severity.WARNING)), True)
f = D.lint_recipe([R.start(200), R.fill(900)])
check("fill over 600 ml -> warning",
      any("over the 600" in x.message.lower() for x in sev(f, Severity.WARNING)), True)

print("\norder matters: each step can be fine and the sequence still wrong")
f = D.lint_recipe([R.start(200), R.vacuum(24, 4), R.fill(250)])
check("extracting before any water is an error",
      any("before any water" in x.message for x in sev(f, Severity.ERROR)), True)
f = D.lint_recipe([R.fill(250), R.start(200), R.vacuum(24, 4)])
check("Start not first is flagged",
      any("not first" in x.message for x in sev(f, Severity.WARNING)), True)
f = D.lint_recipe([R.start(200), R.fill(250), R.start(205), R.vacuum(24, 4)])
check("two Start steps are flagged",
      any("Start steps" in x.message for x in sev(f, Severity.WARNING)), True)
f = D.lint_recipe([R.start(200), R.fill(250), R.vacuum(24, 4), R.dialog("ok?")])
check("ending on a Dialog is flagged",
      any("ends on a Dialog" in x.message for x in sev(f, Severity.WARNING)), True)
f = D.lint_recipe([R.start(200), R.fill(600, rinse_volume_ml=400), R.vacuum(24, 4)])
check("more water than a chamber holds is flagged",
      any("in total" in x.message for x in sev(f, Severity.WARNING)), True)

# and none of that fires on a sound recipe -- a linter that cries wolf gets ignored
f = D.lint_recipe([R.start(200), R.fill(250, rinse_volume_ml=30),
                   R.vacuum(24, 6), R.purge(30, 10, detect=True)])
check("a sound recipe stays clean",
      [x.message for x in f if x.severity >= Severity.WARNING], [])

print("\nfindings are ordered worst-first")
f = D.lint_recipe([R.start(250), R.dialog("")])   # a warning and an error present
check("first finding is the error", f[0].severity, Severity.ERROR)

print("\ndiagnose: error codes resolve to cause + fix")
d = D.diagnose("I got C:3 M:5")
check("names the fault", "sealed" in d.cause.lower() or "seal" in d.summary.lower(), True)
check("gives a fix", len(d.fix) > 10, True)
d = D.diagnose("error C:45 M:2")
check("descale finished recognised", "descale" in (d.cause + d.summary).lower(), True)

print("\ndiagnose: status words and symptoms")
check("'not sealed' status", "chamber" in D.diagnose("it says not sealed").summary.lower(), True)
d = D.diagnose("something totally unknown zzz")
check("unknown symptom asks for more, does not crash",
      "not enough" in d.summary.lower() or "could not" in d.cause.lower(), True)

print("\ndiagnose: unknown code still reports the identifier")
d = D.diagnose("C:88 M:9")
check("keeps the code", "88" in d.summary and "9" in d.summary, True)

print(f"\n{_pass} passed, {_fail} failed")
sys.exit(1 if _fail else 0)

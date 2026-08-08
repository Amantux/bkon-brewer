#!/usr/bin/env python3
"""The add-on's vendored core matches the integration's source.

Runs the standalone check (scripts/check_core_sync.py) as part of the suite, so
`./tests/run_all.sh` and CI both catch drift with no workflow change. The add-on
must build standalone, so the pure logic it needs is vendored into
addon/lightrag_service/bkon_core/; this fails if that copy has drifted.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

print("add-on vendored core is in sync with the integration")
r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_core_sync.py")],
                   capture_output=True, text=True)
sys.stdout.write(r.stdout)
if r.returncode != 0:
    sys.stderr.write(r.stderr)
    print("  FAIL core drift")
    sys.exit(1)
print("1 passed, 0 failed")

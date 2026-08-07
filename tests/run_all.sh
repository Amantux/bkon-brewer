#!/bin/sh
# All unit tests. No network, no Home Assistant, no Bluetooth.
set -e
cd "$(dirname "$0")/.."
for t in tests/test_*.py; do echo "== $t"; python3 "$t"; done

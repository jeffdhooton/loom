#!/usr/bin/env bash
# Create the (gitignored) quickstart sandbox: a tiny git repo with one
# failing test for the coding examples to fix. Idempotent — re-running
# wipes and recreates it.
#
#   bash examples/setup.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox"
rm -rf "$DIR"
mkdir -p "$DIR"

cat > "$DIR/calc.py" << 'PY'
def add(a, b):
    return a - b  # BUG: should be a + b
PY

cat > "$DIR/test_calc.py" << 'PY'
from calc import add


def test_add():
    assert add(2, 3) == 5
PY

git -C "$DIR" init -q -b main
git -C "$DIR" add -A
git -C "$DIR" -c user.email=setpoint@local -c user.name=setpoint commit -q -m "sandbox with failing test"
echo "✓ $DIR ready — try: setpoint run examples/coding.setpoint.yaml"

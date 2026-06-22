#!/usr/bin/env bash
# Bootstrap the (gitignored) working dirs for the loom stress sweep from the
# pristine seeds in this directory. Idempotent: re-running wipes and recreates them.
#
#   bash examples/stress/setup.sh
#
set -euo pipefail

SEED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="$(cd "$SEED_DIR/.." && pwd)"

init_sandbox() {
  local dir="$1"; local seed="$2"; shift 2
  rm -rf "$dir"
  mkdir -p "$dir"
  cp "$SEED_DIR/$seed" "$dir/mathlib.py"
  cp "$SEED_DIR/test_mathlib.py" "$dir/test_mathlib.py"
  for extra in "$@"; do
    cp "$SEED_DIR/$extra" "$dir/$extra"
  done
  git -C "$dir" init -q
  git -C "$dir" add -A
  git -C "$dir" -c user.email=loom@local -c user.name=loom commit -q -m "stress sandbox: buggy mathlib + tests"
  echo "  ✓ $dir ($(git -C "$dir" rev-parse --short HEAD))"
}

echo "Bootstrapping loom stress fixtures…"

# Stage 1 — content: seed the bloated draft into the (worktree-free) out dir.
rm -rf "$EXAMPLES_DIR/stress-out"
mkdir -p "$EXAMPLES_DIR/stress-out"
cp "$SEED_DIR/brief_seed.md" "$EXAMPLES_DIR/stress-out/brief.md"
echo "  ✓ stress-out/brief.md ($(wc -w < "$EXAMPLES_DIR/stress-out/brief.md") words)"

# Stage 2 — coding: multi-bug sandbox (reachable target, markers + bash).
init_sandbox "$EXAMPLES_DIR/stress-sandbox" mathlib_buggy.py

# Stage 2b — blind: same bugs, NO markers; executor denied bash. Forces the outer
# loop to iterate off the VERIFY gate's failing-test feedback.
init_sandbox "$EXAMPLES_DIR/stress-blind-sandbox" mathlib_blind.py

# Stage 3 — endurance: same bugs + one unsatisfiable bonus test.
init_sandbox "$EXAMPLES_DIR/stress-endurance-sandbox" mathlib_buggy.py test_endurance_bonus.py

echo "Done. Now run the sweep (see examples/stress/README.md)."

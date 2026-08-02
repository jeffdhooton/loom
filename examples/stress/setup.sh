#!/usr/bin/env bash
# Bootstrap the (gitignored) working dirs for the setpoint stress sweep from the
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
  git -C "$dir" -c user.email=setpoint@local -c user.name=setpoint commit -q -m "stress sandbox: buggy mathlib + tests"
  echo "  ✓ $dir ($(git -C "$dir" rev-parse --short HEAD))"
}

echo "Bootstrapping setpoint stress fixtures…"

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

# Stage 4 — hidden-oracle feature build: ship ONLY the stub into the sandbox; the
# acceptance suite stays in examples/stress/hidden/ (unreadable to the agent) and is
# run by the gate. Forces multi-iteration self-correction off gate feedback alone.
feat_dir="$EXAMPLES_DIR/stress-feature-sandbox"
rm -rf "$feat_dir"; mkdir -p "$feat_dir"
cp "$SEED_DIR/romans_stub.py" "$feat_dir/romans.py"
git -C "$feat_dir" init -q
git -C "$feat_dir" add -A
git -C "$feat_dir" -c user.email=setpoint@local -c user.name=setpoint commit -q -m "stress feature sandbox: romans stub"
echo "  ✓ $feat_dir ($(git -C "$feat_dir" rev-parse --short HEAD)) — hidden oracle NOT copied in"

echo "Done. Now run the sweep (see examples/stress/README.md)."

# loom stress-test sweep — design

**Date:** 2026-06-22
**Status:** approved, built
**Repo:** `~/workspace/loom`

## Problem

Every prior loom validation (`coding.loom.yaml`, `content.loom.yaml`) **passed on
iteration 1**. The closed-loop machinery — fail → read VERIFY feedback → replan →
fix → re-verify, across many iterations — has therefore never actually been
exercised. We want a stress sweep that *forces* the loop to iterate and converge.

## Key mechanical insight

The loop only iterates when VERIFY fails (`cycle.py`). To stress it, the *starting
state must be guaranteed to fail* and *convergence must take several rounds*. Two
levers:

- **Seed a known-bad starting state** — deterministic, reproducible. Used where a
  guarantee is needed (Stage 1).
- **Hard/narrow target** — rely on the weaker `flash` model not nailing it first try.
  Realistic, used where natural iteration is the point (Stage 2).

## Three staged stress tests

### Stage 1 — Judge self-correction (`stress-content.loom.yaml`)
Reproduces the original 664-word false-positive and proves the two-layer judge gate
now self-corrects. Seed `stress-out/brief.md` with a **~680-word fluff draft**; spec
instructs *read existing draft and revise in place*. Judge gate (`qwen3.6:27b`) with
deterministic `checks: [max_words: 320, min_words: 220, must_not_contain: <buzzwords>]`
plus a subjective rubric (core idea first, 3+ concrete points, actionable takeaway).
→ iter 1 deterministic-fails at ~680 words (no LLM call) → trim into the 220–320 band
while satisfying the rubric → pass.

### Stage 2 — Multi-iter coding self-correction (`stress-coding.loom.yaml`)
`stress-sandbox/` (nested git repo) ships `mathlib.py` with **6 independent bugs**
(add, is_even, factorial, gcd, clamp, mean) + a comprehensive, fully-satisfiable
`test_mathlib.py` (19 tests; 12 fail on the seed). Command gate `pytest -q`, worktree,
`max_iters: 10`, `no_progress_after: 3`, budget `$1.00`.
→ pytest surfaces several failures at once; the loop fixes bugs and re-verifies across
iterations until all green.

### Stage 3 — Endurance / graceful give-up (`stress-endurance.loom.yaml`)
`stress-endurance-sandbox/` = same buggy mathlib **plus** one intentionally
unsatisfiable `test_endurance_bonus.py` (contradicts `test_add_positive`). Command
gate, `max_iters: 20`, `no_progress_after: 6`, budget `$0.50`.
→ the loop fixes every reachable bug, then stops *gracefully* (no_progress / max_iters)
over a long spine, reporting honestly with accurate cumulative budget accounting
instead of spinning forever or faking success. `loom resume` continues the same spine.

## Fixtures & reproducibility

Pristine seeds live (tracked) in `examples/stress/`; mutable working dirs
(`stress-out/`, `stress-sandbox/`, `stress-endurance-sandbox/`) are gitignored and
(re)created from the seeds by `examples/stress/setup.sh` — mirroring the existing
`examples/sandbox/` convention. Existing validated examples are left untouched.

## Verification plan

Run each stage live in order (env ready: DeepSeek key + ollama judge), then read the
`log.md` spine (`loom logs <name>`) and `loom ls` to confirm: Stage 1 self-corrects
length+quality; Stage 2 converges to all-green over >1 iteration; Stage 3 gives up
gracefully and resumes.

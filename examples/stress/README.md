# setpoint stress sweep

A three-stage stress test that exercises the **closed loop itself** — the part every
prior validation skipped, because every prior run passed on iteration 1. Each stage
here is engineered to *fail first and converge over multiple iterations*.

## What's here (tracked, pristine seeds)

| File | Role |
|---|---|
| `mathlib_buggy.py` | math lib with **6 independent bugs** (add, is_even, factorial, gcd, clamp, mean), bugs marked in comments |
| `mathlib_blind.py` | same 6 bugs, **no marker comments** (Stage 2b — executor denied `bash`) |
| `test_mathlib.py` | comprehensive, fully-satisfiable suite (the reachable target) |
| `test_endurance_bonus.py` | one **intentionally unsatisfiable** test (Stage 3 only) |
| `brief_seed.md` | a bloated **~680-word** fluff draft (Stage 1 starting state) |
| `content_rubric.md` | subjective-quality rubric for the judge gate |
| `romans_stub.py` | NotImplementedError stub the Stage 4 agent must implement |
| `hidden/test_romans.py` | **hidden acceptance oracle** (Stage 4) — agent can't read or run it |
| `setup.sh` | bootstraps the gitignored working dirs from these seeds |

The mutated working dirs (`stress-out/`, `stress-sandbox/`, `stress-endurance-sandbox/`)
are **gitignored** — recreate them any time with `setup.sh`.

## Run it

```bash
cd loom && . .venv/bin/activate
bash examples/stress/setup.sh                          # bootstrap working dirs

# Stage 1 — judge self-correction (680w fluff → 220–320w quality brief).
#   needs DEEPSEEK_API_KEY + local ollama (qwen3.6:27b)
setpoint run examples/stress-content.setpoint.yaml --fresh

# Stage 2 — coding self-correction (fix 6 bugs → pytest green; has bash + markers).
setpoint run examples/stress-coding.setpoint.yaml --fresh

# Stage 2b — BLIND coding (no bash, no markers; gate feedback is the only signal).
setpoint run examples/stress-coding-blind.setpoint.yaml --fresh

# Stage 3 — endurance / graceful give-up (unsatisfiable target → long spine → stop).
setpoint run examples/stress-endurance.setpoint.yaml --fresh
setpoint resume examples/stress-endurance.setpoint.yaml        # demonstrate resume mid-spine

# Stage 4 — multi-iter self-correction via a HIDDEN oracle (no bash, can't read tests).
setpoint run examples/stress-feature-hidden.setpoint.yaml --fresh

setpoint ls                                                # statuses + spend
setpoint logs stress-coding-multibug                       # read the memory spine
```

## What each stage proves

- **Stage 1** — the two-layer judge gate forces revision instead of false-positive
  passing: iter 1 deterministic-fails on `max_words` (no LLM call) at ~680 words; the
  loop trims into the 220–320 band while satisfying the subjective rubric, then passes.
- **Stage 2** — `pytest -q` surfaces several failures at once; the loop reads the
  output, fixes bugs, and re-verifies across iterations until all green.
- **Stage 3** — against an unsatisfiable target the loop fixes what it can, then stops
  *gracefully* (no_progress / max_iters) over a long spine and reports honestly —
  with accurate cumulative budget accounting — instead of spinning forever or faking
  success. `setpoint resume` continues the same spine.
- **Stage 4** — the executor cannot self-verify (no `bash`) and cannot read the
  acceptance suite (it lives outside the worktree, run by the gate). Its first
  implementation misses edge cases; the gate's failing-test output is the only signal,
  so the outer loop **iterates and self-corrects** to a fully passing module. This is
  the stage that exercises genuine multi-iteration convergence (vs. Stage 3's give-up).

## Findings (live run, 2026-06-22, DeepSeek-v4 + ollama qwen3.6:27b)

| Stage | Status | Iters | Cost | Takeaway |
|---|---|---|---|---|
| 1 content | passed | 1 | $0.01 | judge gate now honest — 681w→263w in-band, buzzword-free, rubric met |
| 2 coding | passed | 1 | $0.00 | one-shot: used bug-marker comments + ran pytest via bash |
| 2b blind | passed | 1 | $0.01 | one-shot **even blind** — `flash` fixed all 6 from static reasoning |
| 3 endurance | stopped | 6 (→12 on resume) | $0.06 | graceful give-up at no_progress; honest "stopped"; budget accounting exact |
| 4 hidden-oracle | passed | **2** | $0.03 | **genuine self-correction**: iter 1 missed `from_roman('MCMXCIV')`; gate leaked it; iter 2 fixed → 62/62 |

**The headline finding:** setpoint's **outer loop only iterates when a single EXECUTE pass
cannot finish *or verify* the task**. Because EXECUTE is itself a full agentic tool-loop,
a capable model (DeepSeek-v4) one-shots small, well-specified tasks — *even when denied
`bash`* (Stage 2b). The outer DISCOVER→PLAN→EXECUTE→VERIFY→ITERATE cycle reliably engages
only when VERIFY is unsatisfiable in one pass (Stage 3, give-up) or the executor **cannot
self-verify** — denied a shell *and* unable to read the acceptance oracle (Stage 4,
convergent self-correction). Stage 4 is the recipe for stressing multi-iteration
self-correction: hide the oracle and remove the executor's ability to run it. Notably the
Stage 4 agent *tried* to build its own test harness and *tried* to read the hidden test —
both denied — which is precisely what forced it onto the gate's feedback.

**Rough edge:** `setpoint resume` restarts iteration numbering (spine showed n = 1..6, 1..6
rather than 1..12). The spine and budget totals are intact; only the per-iter `n` label
duplicates. Candidate fix: seed `n` from `len(existing_iters)` on resume.

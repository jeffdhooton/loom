# loom stress sweep

A three-stage stress test that exercises the **closed loop itself** — the part every
prior validation skipped, because every prior run passed on iteration 1. Each stage
here is engineered to *fail first and converge over multiple iterations*.

## What's here (tracked, pristine seeds)

| File | Role |
|---|---|
| `mathlib_buggy.py` | math lib with **6 independent bugs** (add, is_even, factorial, gcd, clamp, mean) |
| `test_mathlib.py` | comprehensive, fully-satisfiable suite (the reachable target) |
| `test_endurance_bonus.py` | one **intentionally unsatisfiable** test (Stage 3 only) |
| `brief_seed.md` | a bloated **~680-word** fluff draft (Stage 1 starting state) |
| `content_rubric.md` | subjective-quality rubric for the judge gate |
| `setup.sh` | bootstraps the gitignored working dirs from these seeds |

The mutated working dirs (`stress-out/`, `stress-sandbox/`, `stress-endurance-sandbox/`)
are **gitignored** — recreate them any time with `setup.sh`.

## Run it

```bash
cd ~/workspace/loom && . .venv/bin/activate
bash examples/stress/setup.sh                          # bootstrap working dirs

# Stage 1 — judge self-correction (680w fluff → 220–320w quality brief).
#   needs DEEPSEEK_API_KEY + local ollama (qwen3.6:27b)
loom run examples/stress-content.loom.yaml --fresh

# Stage 2 — multi-iter coding self-correction (fix 6 bugs → pytest green).
loom run examples/stress-coding.loom.yaml --fresh

# Stage 3 — endurance / graceful give-up (unsatisfiable target → long spine → stop).
loom run examples/stress-endurance.loom.yaml --fresh
loom resume examples/stress-endurance.loom.yaml        # demonstrate resume mid-spine

loom ls                                                # statuses + spend
loom logs stress-coding-multibug                       # read the memory spine
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
  success. `loom resume` continues the same spine.

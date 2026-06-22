# loom — Context Handoff

**Last updated:** 2026-06-22
**Repo:** `~/workspace/loom` · GitHub `jeffdhooton/loom` (private) · branch `main` @ `c6e9d71`
**Status:** ✅ **Built, tested (50 passing), and validated live end-to-end. Both proving-ground loops passed against the real DeepSeek API + local ollama judge.**

This document is a self-contained orientation for picking the project back up in a fresh session. Read this + the spec + the plan (links below) and you're caught up.

---

## 1. What loom is

A **standalone DeepSeek-v4-powered closed-loop engine** built from the article *"Loops: What Every AI Engineer Needs to Know in 2026"* (sairahul1). It runs the article's cycle — **DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE** — to a verified outcome, watchable live in a tmux shell ("open a shell and have it rip"). DeepSeek-v4 is the cheap brain (the article's thesis: loops are unaffordable on frontier pricing; cheap frontier-class models fix that).

**Posture (decided during brainstorming):**
- **Independent of Hermes.** Built from the article, not bolted into Hermes. Hermes is a *future seam* only (could later create/manage `loom.yaml` specs the way it manages skills). Not a runtime dependency.
- **Spirit over letter** of the article: keep the 5-stage cycle + closed-loop discipline + cheap-DeepSeek thesis; deliberately prefer deterministic command gates over a "separate verifier agent" for code.

**Source docs (in dotfiles, not this repo):**
- Spec: `~/dotfiles/docs/superpowers/specs/2026-06-21-loom-loop-engine-design.md`
- Plan: `~/dotfiles/docs/superpowers/plans/2026-06-21-loom-loop-engine.md` (the 14-task TDD plan this was built from)
- Saved source article: `~/Personal/Content/sources/x/2026-06-09-sairahul1-loops-what-every-ai-engineer-needs-to-know-in-2026.md`
- Auto-memory: `~/.claude/projects/-Users-jeff-dotfiles/memory/project_loom_loop_engine.md`

---

## 2. Architecture

A loop **core** (cycle + eval gate + budget + memory + UI) drives a pluggable **executor** through a tiny interface. v1 ships one native DeepSeek tool-calling executor. The core never imports the OpenAI SDK — only `clients.py`, `executor/deepseek.py`, `gates/judge.py` do. "Port into Hermes / aider later" = just another executor; no core rewrite.

```
loom/
  __main__.py     CLI: run | resume | ls | logs  (+ _build_executor/_build_plan_client, patchable)
  spec.py         LoopSpec + nested cfg dataclasses; load_spec(); validates type/gate, enforces judge!=maker
  budget.py       PRICING table (real DeepSeek $), Usage, Budget (hard cap + 80% warn)
  memory.py       IterRecord, RunState, Memory — resumable state.json (atomic) + human-readable log.md
  workspace.py    Worktree(repo,branch).create()/.cleanup(); prepare_workspace(spec)
  tools/
    __init__.py   Tool, ToolContext, build_registry, shared _fn schema helper
    local.py      read, write, edit, bash, search  (errors returned as strings, never raise)
    external.py   scry (scry CLI), web (trawl CLI) — degrade gracefully if binary absent
  executor/
    base.py       Executor ABC, ExecuteResult, ExecEvent
    deepseek.py   DeepSeekExecutor — tool-calling loop; DeepSeek reasoning-model compat (see §6)
  gates/
    __init__.py   Gate ABC, GateResult, build_gate(spec, judge_client)
    command.py    CommandGate — runs shell cmd in cwd; passed = exit 0
    checks.py     run_checks() — deterministic objective gates (max_words, min_words, must_contain, must_not_contain, matches)
    judge.py      JudgeGate — TWO-LAYER: (1) deterministic checks fail-fast (no LLM call); (2) structured per-criterion LLM judge. passed = checks pass AND score>=threshold AND no self-reported failed criterion
  cycle.py        Cycle.run(cwd) — the 5-stage state machine + stop conditions
  ui.py           StreamUI — rich streaming for tmux (stage/tool/verify/header/summary)
  clients.py      make_deepseek_client (api.deepseek.com), make_judge_client (ollama/OMLX/deepseek)
examples/
  coding.loom.yaml      coding proving ground (command gate)
  content.loom.yaml     content proving ground (judge gate, ollama qwen3.6:27b)
  rubric.md             judge rubric for the content loop
  sandbox/              throwaway nested git repo with a deliberately-buggy add() (gitignored)
tests/                  50 tests, all passing
```

---

## 3. How to run / resume

```bash
cd ~/workspace/loom && . .venv/bin/activate
loom run examples/coding.loom.yaml      # coding loop (needs DEEPSEEK_API_KEY)
loom run examples/content.loom.yaml     # content loop (needs DEEPSEEK_API_KEY + local ollama)
loom run <spec.yaml> --fresh            # wipe prior state and restart
loom resume <spec.yaml>                 # continue (re-run without --fresh; appends to the spine)
loom ls                                 # list runs + status + spend
loom logs <name>                        # the human-readable run log (the memory spine)
pytest -q                               # 50 passing (scoped to tests/)
```

Run state lives in `~/.loom/runs/<name>/{state.json, log.md}` (override root with `LOOM_RUNS_ROOT`).

---

## 4. Live validation (both passed)

| Run | Status | Iters | Cost | Notes |
|---|---|---|---|---|
| `sandbox-fix-add` (coding) | ✅ passed | 1 | $0.0017 | DeepSeek read calc.py, edited the `a-b`→`a+b` bug, ran pytest, command gate green |
| `brief-loop-engineering` (content) | ⚠️ passed score 1.0, but FALSE POSITIVE | 1 | $0.0234 | see judge-hardening note below |

Usage capture confirmed correct (real per-iter $ recorded). The cost-efficiency thesis holds: a full verified loop for fractions of a cent.

### Judge hardening (commit `ab9b1cc`) — important lesson

The content loop's first "pass" was a **false positive**: the brief was **664 words** but the rubric says "Under 400 words", and the local `qwen3.6:27b` judge gave it 1.0 *and fabricated* "stays well under 400 words". LLM judges cannot be trusted on objective, checkable criteria.

Fix shipped: the judge gate is now **two-layer** —
1. **Deterministic `checks:`** (in the spec's `verify` block) enforce objective criteria in code, fail-fast before any LLM call. `examples/content.loom.yaml` now has `checks: [- max_words: 400]`, so the 664-word draft would now correctly FAIL and force a revision.
2. **Structured LLM judge** returns per-criterion `{name, pass, evidence}` + score; a self-reported failed criterion overrides a high score.

**Takeaway for future judge-gate loops:** put every objective/countable criterion in `checks:`; reserve the LLM judge for genuinely subjective quality. Command-gate (coding) loops were always trustworthy (deterministic exit code). **Re-running the content loop live to confirm it now self-corrects (664→revise→<400→pass) is still pending — a good first thing to verify next session.**

---

## 5. Laptop environment (already set up)

- **`DEEPSEEK_API_KEY`**: stored in `~/.secrets.zsh` (chmod 600, untracked), sourced by `~/dotfiles/zsh/.zshrc` (`[ -f "$HOME/.secrets.zsh" ] && source ...`). Available in every shell/process. loom reads `os.environ` first, also loads `.env` via dotenv. **NOTE: the `.zshrc` source-line edit in dotfiles is currently UNCOMMITTED** — commit it when convenient.
- **Tool binaries** all present → loom tools run at full capability: `rg`, `scry` (`~/go/bin/scry`), `trawl` (`~/go/bin/trawl`), `git`.
- **Local judge = ollama** on `http://localhost:11434/v1` (OpenAI-compatible). Models available: `qwen3.6:27b` (default judge), `qwen3.6:35b`, `gemma4:31b`, plus uncensored Qwen variants.
  - qwen3.6/gemma4 are **thinking models** that return empty `content` unless thinking is disabled. loom handles this automatically: `build_gate` passes `extra_body={"reasoning_effort": "none"}` for non-deepseek (local) judges, which makes ollama return clean JSON. (`/no_think` and `think:false` do NOT work via `/v1`; `reasoning_effort:"none"` does.)
  - Override the judge endpoint with `LOOM_JUDGE_BASE_URL` (e.g. OMLX `http://127.0.0.1:8000/v1` if you tunnel the mini's brain via the `hermes-mlx` alias). OMLX is NOT running on this laptop.

---

## 6. Key technical decisions / gotchas

- **DeepSeek API:** base_url `https://api.deepseek.com` (OpenAI-compatible), key `DEEPSEEK_API_KEY`. Models `deepseek-v4-pro` (plan) / `deepseek-v4-flash` (execute). Pricing /1M tok (in `budget.py` PRICING): pro $1.74 in / $3.48 out (cacheRead $0.145); flash $0.14 / $0.28 (cacheRead $0.028). 1M ctx, 384K out, text-only.
- **DeepSeek tool-calling compat (reasoning model) — in `executor/deepseek.py`:**
  - Never set `tool_choice` (unsupported).
  - When echoing the assistant message that carries tool_calls back, include its `reasoning_content` field if present.
  - Pass `content` through as-is (including `None`) on tool-call turns — do NOT coerce to `""`.
- **maker≠checker** is enforced in `load_spec`: judge gate requires `judge_model != execute.model`.
- **Eval gate is pluggable:** `command` (coding, exit-code, free, deterministic) | `judge` (content, LLM rubric, different/cheaper model).

---

## 7. Deferred to v2 (accepted, NOT bugs — see plan §11 + final review)

Intentional non-goals (designed not to block; interfaces leave room):
- **Cadence/automations** (`loom watch`, or a Hermes cron firing `loom run` headless). The engine does iterate-until-true (`/goal`); scheduled re-runs (`/loop`) are deferred.
- **Fleet scale** (orchestrator → specialists → subagents). v1 is single-agent. The executor interface can later spawn sub-loops.
- **Alternative executors** (aider, `hermes -z`, claude) behind the same `Executor` interface.
- **Full Textual TUI** (v1 streams structured output to stdout — more tmux-honest).

Accepted minor hardening (from the opus whole-branch review — fix if/when convenient):
- No path-containment sandbox in tools `_resolve` — a model could write outside the workspace via `../` (consistent with v1 trust model; `bash` is already arbitrary; README has a security note).
- `git worktree add` failure leaks a temp dir; worktree `cleanup()` swallows errors.
- `cache_read_tokens` not counted toward the secondary `max_tokens` cap (USD cap is primary and correct).
- `executor` stores `pricing` but doesn't use it (cost computed in budget/cycle).
- `_discover` reads context files from `workspace.repo`, not the worktree `cwd` (fine for read-only orientation files).

---

## 8. Build process record

Built via subagent-driven TDD (superpowers): 14 tasks, fresh implementer + per-task spec/quality review each, then an opus whole-branch review. ~21 commits (`c4ee836`..`c6e9d71`). The per-task review loop caught and fixed: tilde expansion in load_spec, web-tool missing-arg guard, DeepSeek `content: null` on tool-call turns, plan-prompt history dedupe, and (final review) the content-example write/read path mismatch + `.env` loading + judge≠maker validation + pytest scoping. SDD scratch (briefs/reports/diffs/ledger) was at `/tmp/loom-sdd/` — **ephemeral, may be gone**; the durable record is git history + this doc + the spec/plan.

---

## 9. Natural next directions (when you return)

Pick any; none are started:
1. **Cadence** — `loom watch <spec>` (re-run on an interval) and/or a Hermes cron that fires `loom run` headless and reports to Telegram. This is the article's "automations" block and the most natural next feature.
2. **More real loops** — write `loom.yaml` specs for actual work: a coding loop on scry/book-system, a research loop (trawl+scry → brief), an ops loop. Each is just a YAML file.
3. **Fleet** — an executor that decomposes a goal and spawns child loops (orchestrator pattern).
4. **Polish** — path-containment sandbox option; richer per-iteration cost/telemetry; a Textual TUI; an aider executor for heavier coding loops.
5. **Hermes seam** — let Hermes author/manage loom specs (the original "port in later" idea).

To resume: `cd ~/workspace/loom && . .venv/bin/activate && pytest -q` (expect 50 passing), then read the spec + plan in dotfiles. Everything is committed and pushed.

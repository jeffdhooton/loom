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

## 8b. Stress sweep (branch `stress-test-sweep`, 2026-06-22)

Built + ran a 4-stage stress sweep to exercise the **closed loop itself** (every prior
run passed on iter 1). Specs `examples/stress-*.loom.yaml`; pristine seeds + bootstrap
in `examples/stress/` (mutable working dirs gitignored, recreate with
`bash examples/stress/setup.sh`). Full findings: `examples/stress/README.md`.

| Stage | Status | Iters | Cost | |
|---|---|---|---|---|
| 1 content (judge) | passed | 1 | $0.01 | judge gate now honest: 681w→263w in-band, buzzword-free, rubric met |
| 2 coding (markers+bash) | passed | 1 | $0.00 | one-shot |
| 2b coding (blind, no bash) | passed | 1 | $0.01 | one-shot **even blind** |
| 3 endurance (unsatisfiable) | stopped | 6 →12 resume | $0.06 | graceful no_progress stop, exact accounting |
| 4 hidden-oracle feature build | passed | **2** | $0.03 | **genuine self-correction** — iter1 missed an edge case, gate leaked it, iter2 fixed |

**Headline finding:** loom's **outer loop only iterates when one EXECUTE pass can't
finish/verify the task.** EXECUTE is itself a full agentic tool-loop, so DeepSeek-v4
one-shots small well-specified tasks — even denied `bash` (2b). To stress *convergent*
multi-iteration self-correction (Stage 4): **hide the acceptance oracle** (test outside
the worktree, run by the gate via `PYTHONPATH=. pytest <abs path>`) **and deny `bash`** —
the agent's first attempt misses edge cases, the gate leaks them, it self-corrects.
Stage 3 (unsatisfiable) covers the give-up path. Stage 1 confirms the two-layer judge
gate is no longer a false-positive risk (the original pending validation).

**Rough edge found:** `loom resume` restarts iteration numbering (spine showed n=1..6,1..6
not 1..12); spine + budget totals intact. Candidate fix: seed `n` from `len(existing_iters)`.

## 9. Natural next directions (when you return)

Pick any; none are started:
1. **Cadence** — `loom watch <spec>` (re-run on an interval) and/or a Hermes cron that fires `loom run` headless and reports to Telegram. This is the article's "automations" block and the most natural next feature.
2. **More real loops** — write `loom.yaml` specs for actual work: a coding loop on scry/book-system, a research loop (trawl+scry → brief), an ops loop. Each is just a YAML file.
3. **Fleet** — an executor that decomposes a goal and spawns child loops (orchestrator pattern).
4. **Polish** — path-containment sandbox option; richer per-iteration cost/telemetry; a Textual TUI; an aider executor for heavier coding loops.
5. **Hermes seam** — let Hermes author/manage loom specs (the original "port in later" idea).

To resume: `cd ~/workspace/loom && . .venv/bin/activate && pytest -q` (expect 50 passing), then read the spec + plan in dotfiles. Everything is committed and pushed.

---

## 10. Phase A — multi-engine executors (2026-07-17, branch `feat/multi-engine-executors`)

Built via subagent-driven SDD (9 tasks; brief/report/spec-coverage per task at
`.superpowers/sdd/task-*-brief.md`). Adds Claude/Codex as alternative EXECUTE
engines and a `deliver` connector that opens a PR on green — loom is no longer
DeepSeek-only or dead-ended at a passing gate. `pytest -q` now shows **78
passing** (was 50). Not yet merged to `main`.

**What shipped:**
- **`execute.engine: deepseek | claude | codex`** (`loom/spec.py::VALID_ENGINES`,
  dispatched in `loom/__main__.py::_build_executor`). `claude`/`codex` shell
  out to the CLI (`AgentCLIExecutor` in `loom/executor/agent_cli.py`,
  concrete `ClaudeExecutor`/`CodexExecutor`) and let the agent own its own
  tool use (read/write/edit/bash) inside the workspace — loom just composes
  the prompt, sets `cwd`, and parses stdout for text + usage. A failed or
  timed-out agent subprocess **never raises**; it comes back as an unproductive
  `ExecuteResult` and the gate fails it like any other bad iteration (verified
  live: killing/erroring the stub agent just fails VERIFY, no crash).
- **Zero-cost PLAN pass-through for agent engines**
  (`loom/executor/agent_plan.py::AgentPlanClient`) — the agent plans
  internally during EXECUTE, so PLAN is a stub that keeps `cycle.py`
  unchanged. Because `claude`/`codex` are subscription engines, `budget.py`
  prices both at `$0` (`PRICING["claude"]`/`PRICING["codex"]`) — they are
  **unmetered on tokens**, so agent-engine loops are governed by
  `stop.max_iters` + `stop.wall_clock_secs` instead of `budget.max_usd`.
  `Budget.should_stop()` now also checks wall-clock elapsed
  (`loom/budget.py`).
- **`verify.judge_engine: claude | codex`** (`loom/spec.py::VALID_JUDGE_ENGINES`,
  wired in `loom/clients.py::make_judge_client`) runs the judge gate as a
  **fresh, read-only** agent process — `claude -p ... --permission-mode plan`
  / `codex exec --sandbox read-only` (`loom/gates/agent_judge.py::AgentJudgeClient`)
  — so the grader is a different engine than the one that did the work, and
  it cannot edit. The OpenAI-shaped response wrapper means `JudgeGate`
  (`loom/gates/judge.py`) parses its stdout unchanged.
- **`@diff` artifact** (`loom/gates/judge.py::JudgeGate._read_artifact`) — when
  `deliver.artifact: "@diff"`, the judge gate reviews `git diff HEAD` instead
  of a single output file, so a coding loop's changes (not just a content
  file) can be agent-graded.
- **`deliver:` connector** (`loom/deliver.py`) — on a **passed** run: branch
  (`git checkout -B`), commit, optional push + `gh pr create` (base `main`),
  optional sheet note via `gog`, optional `notify` flag. **Never merges,
  never deploys** — `deliver.merge` is rejected both at spec load
  (`loom/spec.py::load_spec`) and again defensively inside `deliver()`
  itself; every side-effecting subprocess call is restricted to an
  **allow-list on the command verb** (`git`/`gh`/`gog`, `ALLOWED_VERBS` in
  `loom/deliver.py`) rather than a text scan of PR titles/bodies, so a
  goal string containing the word "merge" can't trip a false guard or be
  used to smuggle a disallowed verb. On a non-passed run, `deliver` instead
  writes `report.md` (goal, status, per-iteration pass/fail + feedback) and
  takes no git action.
- **Proving ground:** `examples/agent-coding.loom.yaml` (agent engine,
  command gate, `deliver.push/pr: false` for local-only) +
  `scripts/agent-smoke.sh`, which drops a stub `claude` CLI on `PATH` that
  fixes the sandbox bug and prove the full loop — DISCOVER→...→ITERATE,
  budget $0.00, `deliver` opening a local branch — closes offline with no
  real model or network call. Re-ran live during this handoff: passed in 1
  iteration, `delivered: branch loop/agent-sandbox-fix, notify`, exit 0.

**Key files:** `loom/spec.py` (engine/judge_engine/wall_clock_secs/deliver.merge
guard), `loom/budget.py` (wall-clock stop, zero-cost agent pricing),
`loom/executor/agent_cli.py` + `agent_plan.py`, `loom/gates/agent_judge.py`,
`loom/gates/judge.py` (`@diff`), `loom/deliver.py`, `loom/__main__.py`
(`_build_executor`/`_build_plan_client` dispatch + judge-engine wiring +
deliver call site), `examples/agent-coding.loom.yaml`, `scripts/agent-smoke.sh`.

**Open items:**
1. ✅ **DONE 2026-07-17 — live test passed (both engines, merged `ab856bf`).**
   Claude flags were correct as-is; Codex needed `--sandbox workspace-write` +
   `stdin=DEVNULL` (commit `adad248`). Headless auth works for both. Full record:
   `~/dotfiles/docs/superpowers/2026-07-17-loom-resume-and-phase-b-handoff.md` §2.4.
   Still to do: one live cross-engine JUDGE-gate run before trusting the grader
   unattended (the original item text below is kept for reference).
   **Confirm real CLI flags + headless auth before the first live overnight
   run.** `agent_cli.py` and `agent_judge.py` were built and tested against
   *assumed* flag shapes (`claude -p ... --output-format json
   --permission-mode acceptEdits` / `--permission-mode plan`; `codex exec
   --json` / `codex exec --sandbox read-only`) and mocked/stubbed subprocess
   runners — never against the real `claude`/`codex` binaries. Before
   trusting an unattended run: verify these flags exist on the installed CLI
   versions, that `--permission-mode acceptEdits` actually allows
   file-editing without an interactive prompt, that `--sandbox read-only`
   truly blocks writes for the judge, and that headless auth (no browser
   popup, no interactive login) works in a non-interactive shell/cron
   context.
**Fixed in final review (commit `2abb996`):** the four items below were found
by the whole-branch review and resolved before merge (85 tests):
- **C1 — `deliver.branch: main` now rejected** at `load_spec` and defensively
  in `deliver()` (disallows `main`/`master`), closing the push-to-trunk gap.
- **I1 — failure-path `report.md` now durable:** `deliver(report_dir=...)` is
  passed `memory.root` (`~/.loom/runs/<name>/`) by `cmd_run`, so the report
  survives worktree cleanup instead of being deleted with the temp tree.
- **I2 — cross-engine judge enforced:** when `verify.judge_engine` is set it
  must differ from `execute.engine` (agent judges ignore `judge_model`, so the
  old model-only check was bypassable).
- **I3 — missing `claude`/`codex` binary no longer raises:** `FileNotFoundError`
  is caught in `agent_cli.py` (unproductive result) and `agent_judge.py`
  (fails closed, `"{}"`).

**Still open:** item 1 above (confirm real CLI flags + headless auth) remains
the one genuine pre-first-run gate. Plus these non-blocking follow-up nits:
   no e2e test for the `cmd_run`→`deliver`
   `report_dir` wiring; `@diff` ignores `git diff` returncode; dead top-level
   `make_deepseek_client` import (shadowed); `_check_no_merge` matches only
   `argv[1:3]`; smoke script `set -e` echo + BSD `sed`; a single agent turn
   (`timeout` default 1800s) can overrun a smaller `wall_clock_secs` (soft,
   between-iteration cap).

**Next session — resume here:** the live test (real `claude -p`/`codex exec`
flags + headless auth, then a real single-loop run) and Phase B (fleet
supervisor + portable `loop` skill + scribe fleet) are laid out step-by-step in
`~/dotfiles/docs/superpowers/2026-07-17-loom-resume-and-phase-b-handoff.md`.

## 11. Phase B — fleet supervisor (2026-07-17, branch `feat/fleet-supervisor`)

Built via subagent-driven SDD (7 tasks; brief/report/spec-coverage per task at
`.superpowers/sdd/task-*-brief.md`). Adds a fleet layer on top of the
single-member `run_loop` engine: run N member specs concurrently, each in its
own isolated worktree, with a shared kill switch and a live dashboard.
`pytest -q` shows **97 passing** (was 78 after Phase A). Not yet merged to
`main`.

**What shipped:**
- **`loom fleet run <fleet.yaml> [--fresh]`** (`loom/fleet.py::run_fleet`) —
  loads a `FleetSpec` (`name`, `members: [...]`, `concurrency`), then runs
  every member's `run_loop` inside a `ThreadPoolExecutor(max_workers=concurrency)`.
  Threads are safe because each member gets its own worktree via the existing
  `prepare_workspace`/`Worktree` machinery (Task 1/4) — no shared mutable
  state between members beyond the fleet-level STOP sentinel and the shared
  thread pool itself.
- **Worktree-per-member isolation** — no new isolation code was needed; the
  fleet layer reuses `run_loop`'s existing per-spec `workspace.worktree: true`
  handling. Two members pointed at the *same* `workspace.repo` but different
  `workspace.branch` values each get their own worktree + branch and cannot
  see each other's edits (proved by Task 7's smoke, see below).
- **`loom fleet stop`** + STOP sentinel (`fleet.stop_sentinel_path()` →
  `~/.loom/STOP`) — v1 kill-switch semantics: writing the sentinel **halts
  scheduling** (no new member is submitted; unstarted members are recorded as
  `"skipped"`) and each in-flight member **aborts at its own next iteration
  boundary** via `abort_check=lambda: sentinel.exists()` threaded through
  `run_loop` → `Cycle` (`loom/cycle.py`, checked once per iteration). This is
  **not** a hard kill of in-flight agent subprocesses — a running `claude -p`
  / `codex exec` call is allowed to finish its current turn (bounded by the
  member's own `stop.wall_clock_secs`/timeout) before the loop notices the
  sentinel and exits. A stale sentinel from a previous run is cleared at the
  start of every `run_fleet()` call so a fresh fleet is never pre-blocked.
- **`loom fleet status <fleet.yaml>`** (`fleet.fleet_status`) — renders a
  table (member, status, iters, spend) from each member's `~/.loom/runs/<name>/state.json`
  and writes it to `~/.loom/fleets/<fleet-name>/status.md` as a durable
  dashboard.
- **Backpressure via semaphore** — `run_fleet` uses a `threading.Semaphore(concurrency)`
  ahead of `ThreadPoolExecutor.submit()` so the STOP check before submitting
  member N+1 reflects genuinely completed work (a released slot), not just
  "enqueued" work — otherwise the skip-unstarted-members behavior would be
  racy/nondeterministic.

**Key files:** `loom/fleet.py` (`run_fleet`, `fleet_status`, `stop_sentinel_path`,
`_member_name`, `_run_member`), `loom/fleet_spec.py` (`FleetSpec`, `load_fleet`),
`loom/__main__.py::cmd_fleet` (`fleet run|status|stop` dispatch) — plus the
`run_loop`/`Cycle` `abort_check` parameter added in Task 1 and reused here
unchanged. `examples/fleet-demo.yaml`, `examples/agent-coding-b.loom.yaml`,
`scripts/fleet-smoke.sh` (Task 7).

**Task 7 smoke (offline, no real model):** `scripts/fleet-smoke.sh` puts a
stub `claude` on `PATH` (same shape as Phase A's `agent-smoke.sh`), resets
the sandbox bug, prunes stale worktrees, then runs `loom fleet run
examples/fleet-demo.yaml --fresh` — two members (`agent-coding.loom.yaml`
and `agent-coding-b.loom.yaml`) pointed at the **same** `examples/sandbox`
repo but **different** branches (`loop/agent-sandbox-fix` /
`loop/agent-sandbox-fix-b`). Confirmed live: both members ran in parallel,
each got its own worktree, the stub fixed each worktree's own `calc.py`
independently, both delivered — `loop/agent-sandbox-fix` and
`loop/agent-sandbox-fix-b` each carry the fix, `examples/sandbox` `main` is
untouched, and both members' `~/.loom/runs/<name>/state.json` show
`"status": "passed"`. This proves the isolation claim end to end.

**Known bug found by the Task 7 smoke (not patched — Phase B code, out of
scope for a smoke-test task):** `loom fleet status` printed `pending` for
both members even though both had actually passed. Root cause:
`fleet.py::_member_name()` (used by both `run_fleet`'s result dict and
`fleet_status`'s per-member `state.json` lookup) derives the run's name from
the **member YAML filename** (`member_path.stem.replace(".loom", "")` — e.g.
`agent-coding.loom.yaml` → `"agent-coding"`), but `run_loop`/`Memory` actually
key each run's `~/.loom/runs/<name>/` directory by the spec's **declared
`name:` field** (loaded via `load_spec`), which is not required to match the
filename — and doesn't, for the existing `agent-coding.loom.yaml`
(`name: agent-sandbox-fix`) and the new `agent-coding-b.loom.yaml`
(`name: agent-sandbox-fix-b`). The existing unit tests
(`tests/test_fleet.py`) don't catch this because every fixture there
constructs `member.loom.yaml` files whose filename stem is made to equal the
mocked spec's `name`, which never exercises the mismatch. **Fix (deferred to
a follow-up task, not done here):** `fleet.py` should `load_spec(member_path)`
and use `spec.name` (with a fallback to the filename if the load fails) for
both the `run_fleet()` result-dict key and the `fleet_status()` lookup,
instead of `_member_name()`'s filename-only derivation.

from __future__ import annotations

import os
import sys
from pathlib import Path

from loom.clients import make_deepseek_client


def _runs_root() -> Path:
    return Path(os.environ.get("LOOM_RUNS_ROOT", str(Path.home() / ".loom" / "runs")))


def _build_executor(spec):
    engine = spec.execute.engine
    if engine == "claude":
        from loom.executor import ClaudeExecutor
        return ClaudeExecutor()
    if engine == "codex":
        from loom.executor import CodexExecutor
        return CodexExecutor()
    from loom.clients import make_deepseek_client
    from loom.executor import DeepSeekExecutor
    from loom.budget import PRICING
    return DeepSeekExecutor(client=make_deepseek_client(), pricing=PRICING)


def _build_plan_client(spec):
    if spec.execute.engine in ("claude", "codex"):
        from loom.executor.agent_plan import AgentPlanClient
        return AgentPlanClient()
    from loom.clients import make_deepseek_client
    return make_deepseek_client()


def run_loop(spec, *, fresh: bool = False, ui=None, abort_check=None):
    from loom.workspace import prepare_workspace
    from loom.budget import Budget, PRICING
    from loom.memory import Memory
    from loom.gates import build_gate
    from loom.clients import make_judge_client
    from loom.ui import StreamUI
    from loom.cycle import Cycle

    memory = Memory(spec.name, root=_runs_root())
    if fresh:
        import shutil
        if memory.root.exists():
            shutil.rmtree(memory.root)

    budget = Budget(spec.budget.max_usd, spec.budget.max_tokens, PRICING,
                     wall_clock_secs=spec.stop.wall_clock_secs)
    if ui is None:
        ui = StreamUI(name=spec.name, budget=budget)
    ui.header()

    judge_client = (make_judge_client(spec.verify.judge_model, engine=spec.verify.judge_engine)
                    if spec.verify.gate == "judge" else None)
    gate = build_gate(spec, judge_client=judge_client)
    executor = _build_executor(spec)
    plan_client = _build_plan_client(spec)

    cwd, wt = prepare_workspace(spec)
    try:
        cycle = Cycle(spec, executor, gate, memory, budget, ui, plan_client,
                      abort_check=abort_check)
        state = cycle.run(cwd=cwd)

        # deliver() must run while `cwd` still exists — a worktree cwd is
        # removed by wt.cleanup() below, so this has to happen inside the try.
        if getattr(spec, "deliver", None):
            from loom.deliver import deliver as _deliver
            # report_dir=memory.root: for `worktree: true` runs, cwd is a temp
            # worktree removed by wt.cleanup() in this finally block, so a
            # failure-path report.md must land somewhere durable instead.
            result = _deliver(spec, cwd, state, report_dir=memory.root)
            if result.delivered:
                print(f"delivered: {', '.join(result.actions)}"
                      + (f" — {result.pr_url}" if result.pr_url else ""))
            elif result.report_path:
                print(f"not delivered — report at {result.report_path}")
    finally:
        if wt is not None:
            wt.cleanup()
    return state


def cmd_run(spec_path: str, fresh: bool = False) -> int:
    from loom.spec import load_spec
    spec = load_spec(spec_path)
    state = run_loop(spec, fresh=fresh)
    return 0 if state.status == "passed" else 2


def cmd_ls() -> int:
    root = _runs_root()
    if not root.exists():
        print("no runs yet")
        return 0
    import json
    for d in sorted(root.iterdir()):
        sp = d / "state.json"
        if sp.exists():
            s = json.loads(sp.read_text())
            print(f"{s['name']:30} {s['status']:18} "
                  f"iters={len(s.get('iters', []))} ${s.get('spent_usd', 0):.2f}")
    return 0


def cmd_logs(name: str) -> int:
    log = _runs_root() / name / "log.md"
    if not log.exists():
        print(f"no log for {name}", file=sys.stderr)
        return 1
    print(log.read_text())
    return 0


def cmd_fleet(rest: list[str]) -> int:
    from loom import fleet
    if not rest:
        print("fleet: usage: loom fleet {run <fleet.yaml> [--fresh] | status <fleet.yaml> | stop}",
              file=sys.stderr)
        return 1
    sub, args = rest[0], rest[1:]
    if sub == "stop":
        path = fleet.stop_sentinel_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stop")
        print(f"fleet stop requested — sentinel at {path}")
        return 0
    if not args:
        print(f"fleet {sub}: missing fleet.yaml", file=sys.stderr)
        return 1
    if sub == "run":
        results = fleet.run_fleet(args[0], fresh=("--fresh" in args))
        print(fleet.fleet_status(args[0]))
        return 0 if all(v == "passed" for v in results.values()) else 2
    if sub == "status":
        print(fleet.fleet_status(args[0]))
        return 0
    print(f"unknown fleet subcommand: {sub}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print("loom — DISCOVER->PLAN->EXECUTE->VERIFY->ITERATE loop engine")
        print("usage: loom {run <spec.yaml> [--fresh] | resume <spec.yaml> | ls | logs <name> | "
              "fleet run|status|stop}")
        return 0

    cmd, rest = argv[0], argv[1:]
    if cmd in ("run", "resume"):
        if not rest:
            print(f"{cmd}: missing spec path", file=sys.stderr)
            return 1
        return cmd_run(rest[0], fresh=("--fresh" in rest))
    if cmd == "ls":
        return cmd_ls()
    if cmd == "logs":
        if not rest:
            print("logs: missing run name", file=sys.stderr)
            return 1
        return cmd_logs(rest[0])
    if cmd == "fleet":
        return cmd_fleet(rest)
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import sys
from pathlib import Path


def _runs_root() -> Path:
    return Path(os.environ.get("LOOM_RUNS_ROOT", str(Path.home() / ".loom" / "runs")))


def _build_executor(spec):
    from loom.clients import make_deepseek_client
    from loom.executor import DeepSeekExecutor
    from loom.budget import PRICING
    return DeepSeekExecutor(client=make_deepseek_client(), pricing=PRICING)


def _build_plan_client():
    from loom.clients import make_deepseek_client
    return make_deepseek_client()


def cmd_run(spec_path: str, fresh: bool = False) -> int:
    from loom.spec import load_spec
    from loom.workspace import prepare_workspace
    from loom.budget import Budget, PRICING
    from loom.memory import Memory
    from loom.gates import build_gate
    from loom.clients import make_judge_client
    from loom.ui import StreamUI
    from loom.cycle import Cycle

    spec = load_spec(spec_path)
    memory = Memory(spec.name, root=_runs_root())
    if fresh:
        import shutil
        if memory.root.exists():
            shutil.rmtree(memory.root)

    budget = Budget(spec.budget.max_usd, spec.budget.max_tokens, PRICING)
    ui = StreamUI(name=spec.name, budget=budget)
    ui.header()

    judge_client = (make_judge_client(spec.verify.judge_model)
                    if spec.verify.gate == "judge" else None)
    gate = build_gate(spec, judge_client=judge_client)
    executor = _build_executor(spec)
    plan_client = _build_plan_client()

    cwd, wt = prepare_workspace(spec)
    try:
        cycle = Cycle(spec, executor, gate, memory, budget, ui, plan_client)
        state = cycle.run(cwd=cwd)
    finally:
        if wt is not None:
            wt.cleanup()
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print("loom — DISCOVER->PLAN->EXECUTE->VERIFY->ITERATE loop engine")
        print("usage: loom {run <spec.yaml> [--fresh] | resume <spec.yaml> | ls | logs <name>}")
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
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

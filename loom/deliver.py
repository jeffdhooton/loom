from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# loom never deploys — deploys are manual (see repo CLAUDE.md). Any emitted
# command whose joined string contains one of these phrases is refused before
# it reaches the runner.
DENYLIST: tuple[str, ...] = ("fly deploy", "deploy")


@dataclass
class DeliverResult:
    delivered: bool
    pr_url: str | None = None
    report_path: str | None = None
    actions: list[str] = field(default_factory=list)


def _check_denylist(argv: list[str]) -> None:
    joined = " ".join(str(a) for a in argv)
    for phrase in DENYLIST:
        if phrase in joined:
            raise ValueError(f"refusing to emit command containing denylisted phrase {phrase!r}: {joined}")


def _check_no_merge(argv: list[str]) -> None:
    joined = " ".join(str(a) for a in argv)
    if "pr merge" in joined or (len(argv) >= 2 and argv[0] == "gh" and argv[1] == "merge"):
        raise ValueError(f"refusing to emit a merge command: {joined}")


def _run(runner, argv: list[str], cwd: Path):
    _check_no_merge(argv)
    _check_denylist(argv)
    return runner(argv, cwd=str(cwd), capture_output=True, text=True)


def _write_report(spec, cwd: Path, state) -> str:
    lines = [f"# loom report — {spec.name}", "", f"**Goal:** {spec.goal}",
             f"**Status:** {state.status}", "", "## Iterations"]
    for it in state.iters:
        mark = "PASS" if getattr(it, "passed", False) else "FAIL"
        lines.append(f"- iter {it.n}: {mark} — {getattr(it, 'feedback', '')}")
    path = cwd / "report.md"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def deliver(spec, cwd: Path, state, runner=subprocess.run) -> DeliverResult:
    """Branch -> commit -> (push) -> (PR) -> (sheet) -> (notify), gated on a
    passed run. NEVER merges to main, NEVER deploys. All side-effecting calls
    go through `runner` so callers can fully mock git/gh/gog in tests.
    """
    d = spec.deliver or {}
    if d.get("merge"):
        # Defense in depth: loom.spec.load_spec already refuses `deliver.merge`
        # at load time, but deliver() must independently refuse it too, since
        # it can be called directly (e.g. from tests or future call sites)
        # without going through load_spec.
        raise ValueError("deliver.merge must be false — loom never merges to main")

    if state.status != "passed":
        return DeliverResult(delivered=False, report_path=_write_report(spec, cwd, state))

    actions: list[str] = []
    branch = d.get("branch") or f"loop/{spec.name}"

    _run(runner, ["git", "checkout", "-B", branch], cwd)
    _run(runner, ["git", "add", "-A"], cwd)
    _run(runner, ["git", "commit", "-m", f"loom: {spec.name} — {spec.goal[:60]}"], cwd)
    actions.append(f"branch {branch}")

    pr_url = None
    if d.get("push", True):
        _run(runner, ["git", "push", "-u", "origin", branch], cwd)
        actions.append("push")
    if d.get("pr", True):
        body = (f"Autonomous loom run for {spec.name}.\n\n"
                 f"Goal: {spec.goal}\n\nVerifier + grader passed. Review before merge.")
        proc = _run(runner, ["gh", "pr", "create", "--base", "main",
                             "--head", branch, "--title", f"{spec.name}: {spec.goal[:60]}",
                             "--body", body], cwd)
        pr_url = (proc.stdout or "").strip() or None
        actions.append("pr")
    if d.get("sheet_task"):
        # Update the Google Sheet tracker via the `gog` CLI (the `status`
        # skill's wrapper around `gog sheets`). The concrete subcommand can be
        # aligned to the status skill's exact invocation without breaking the
        # deliver contract, as long as the task id appears in the command.
        note = f"loom: PR opened for {d['sheet_task']}" + (f" {pr_url}" if pr_url else "")
        _run(runner, ["gog", "sheets", "note", d["sheet_task"], note], cwd)
        actions.append(f"sheet {d['sheet_task']}")
    if d.get("notify"):
        actions.append("notify")

    return DeliverResult(delivered=True, pr_url=pr_url, actions=actions)

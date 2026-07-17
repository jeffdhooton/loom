from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# loom never deploys and never merges — deploys are manual (see repo
# CLAUDE.md), merges are human-reviewed. deliver() only ever legitimately
# emits git/gh/gog commands, so the guard is a structural allow-list on the
# command verb (argv[0]), not a substring scan of free-text arguments (PR
# titles/bodies and commit messages are derived from spec.goal and must not
# be able to trip a text-based denylist).
ALLOWED_VERBS: tuple[str, ...] = ("git", "gh", "gog")


@dataclass
class DeliverResult:
    delivered: bool
    pr_url: str | None = None
    report_path: str | None = None
    actions: list[str] = field(default_factory=list)


def _check_allowed_verb(argv: list[str]) -> None:
    verb = argv[0] if argv else None
    if verb not in ALLOWED_VERBS:
        joined = " ".join(str(a) for a in argv)
        raise ValueError(f"refusing to emit command with disallowed verb {verb!r}: {joined}")


def _check_no_merge(argv: list[str]) -> None:
    if argv and argv[0] == "gh" and "merge" in argv[1:3]:
        joined = " ".join(str(a) for a in argv)
        raise ValueError(f"refusing to emit a merge command: {joined}")


def _run(runner, argv: list[str], cwd: Path):
    _check_allowed_verb(argv)
    _check_no_merge(argv)
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

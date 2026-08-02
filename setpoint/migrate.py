from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

LEGACY_DIR = ".loom"
NEW_DIR = ".setpoint"
LEGACY_EXT = ".loom.yaml"
NEW_EXT = ".setpoint.yaml"

# Path-ish token ending in .loom.yaml, e.g. "alpha.loom.yaml",
# "sub/x.loom.yaml", "../other/x.loom.yaml".
_REF_PATTERN = re.compile(r"[A-Za-z0-9_./-]+\.loom\.yaml")


class MigrationBlocked(RuntimeError):
    """Raised by apply_migration when the plan has unresolved problems."""


@dataclass
class MigrationPlan:
    repo: Path
    spec_dir: Path | None = None
    spec_renames: list[tuple[Path, Path]] = field(default_factory=list)
    body_rewrites: list[Path] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.spec_dir is None

    @property
    def is_blocked(self) -> bool:
        return bool(self.problems)


def _is_tracked(repo: Path, path: Path) -> bool:
    if not (repo / ".git").exists():
        return False
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=repo, capture_output=True, text=True)
    return proc.returncode == 0


def plan_migration(repo: Path) -> MigrationPlan:
    repo = Path(repo).expanduser().resolve()
    spec_dir = repo / LEGACY_DIR
    if not spec_dir.is_dir():
        return MigrationPlan(repo=repo)

    renames = [
        (p, p.with_name(p.name[: -len(LEGACY_EXT)] + NEW_EXT))
        for p in sorted(spec_dir.glob("*" + LEGACY_EXT))
    ]
    # Fleet specs are named fleet.yaml — they never match *.loom.yaml and are
    # never renamed, but they list their members by filename in their BODY.
    # Missing this leaves every fleet pointing at files that no longer exist.
    rewrites = [
        p for p in sorted(spec_dir.glob("*.yaml"))
        if LEGACY_EXT in p.read_text()
    ]

    problems: list[str] = []

    new_dir = repo / NEW_DIR
    if new_dir.exists():
        problems.append(f"{NEW_DIR}/ already exists")

    for _src, dst in renames:
        if dst.exists():
            problems.append(f"{dst.name} would be overwritten")

    # A fleet's body may reference a member outside this migration's scope
    # (nested under a subdirectory, or via a relative path elsewhere). The
    # non-recursive rename glob above will not touch that file, but a naive
    # body rewrite would still rename the reference text — pointing a
    # working fleet at a file that was never renamed.
    rename_sources = {src.resolve() for src, _ in renames}
    for p in rewrites:
        seen: set[str] = set()
        for ref in _REF_PATTERN.findall(p.read_text()):
            if ref in seen:
                continue
            seen.add(ref)
            resolved = (spec_dir / ref).resolve()
            if resolved not in rename_sources:
                problems.append(
                    f"{p.name} references {ref}, which this migration will not rename")

    return MigrationPlan(repo=repo, spec_dir=spec_dir,
                         spec_renames=renames, body_rewrites=rewrites,
                         problems=problems)


def render_plan(plan: MigrationPlan) -> str:
    if plan.is_blocked:
        lines = [f"REFUSING — {len(plan.problems)} problems:"]
        for problem in plan.problems:
            lines.append(f"  {problem}")
        lines.append("")
        lines.append("nothing was changed")
        return "\n".join(lines)
    if plan.is_empty:
        return f"no {LEGACY_DIR}/ directory in {plan.repo} — nothing to migrate"
    lines = [f"{LEGACY_DIR}/ -> {NEW_DIR}/"]
    if plan.spec_renames:
        lines.append(f"  {len(plan.spec_renames)} specs -> *{NEW_EXT}")
    for p in plan.body_rewrites:
        n = p.read_text().count(LEGACY_EXT)
        lines.append(f"  {p.name}: {n} member ref(s) rewritten")
    lines.append("  not committed — review and commit yourself")
    return "\n".join(lines)


def _move(repo: Path, src: Path, dst: Path) -> None:
    if _is_tracked(repo, src):
        subprocess.run(["git", "mv", str(src), str(dst)],
                       cwd=repo, check=True, capture_output=True)
    else:
        shutil.move(str(src), str(dst))


def apply_migration(plan: MigrationPlan) -> list[str]:
    """Rewrite bodies, rename specs, then rename the directory. Never commits."""
    if plan.is_blocked:
        raise MigrationBlocked(
            "refusing to migrate — " + "; ".join(plan.problems))
    if plan.is_empty:
        return []
    actions: list[str] = []

    # 1. Bodies first — content does not depend on path, and doing it here
    #    means every later step operates on paths that still exist.
    for p in plan.body_rewrites:
        p.write_text(p.read_text().replace(LEGACY_EXT, NEW_EXT))
        actions.append(f"rewrote member refs in {p.name}")

    # 2. Spec files, still inside the legacy directory.
    for src, dst in plan.spec_renames:
        _move(plan.repo, src, dst)
        actions.append(f"{src.name} -> {dst.name}")

    # 3. The directory itself.
    _move(plan.repo, plan.spec_dir, plan.repo / NEW_DIR)
    actions.append(f"{LEGACY_DIR}/ -> {NEW_DIR}/")
    return actions

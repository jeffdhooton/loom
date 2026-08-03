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
# The directory is renamed too, so a body that points at a NON-spec file inside
# it (rubric, script, corpus) dangles unless we rewrite the directory segment
# as well. Matching the literal ".loom/" is deliberately narrow: a workspace
# path like ".../program-health-loom/" contains "-loom/", not ".loom/".
LEGACY_DIR_REF = LEGACY_DIR + "/"
NEW_DIR_REF = NEW_DIR + "/"

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
    def _has_legacy_ref(p: Path) -> bool:
        text = p.read_text()
        return LEGACY_EXT in text or LEGACY_DIR_REF in text

    # Fleet specs are named fleet.yaml — they never match *.loom.yaml and are
    # never renamed, but they list their members by filename in their BODY.
    # Missing this leaves every fleet pointing at files that no longer exist.
    # LEGACY_DIR_REF catches the other half: bodies pointing at non-spec files
    # inside the directory (rubrics, scripts, corpora), which move with it.
    rewrites = [
        p for p in sorted(spec_dir.glob("*.yaml"))
        if _has_legacy_ref(p)
    ]

    problems: list[str] = []

    new_dir = repo / NEW_DIR
    # is_symlink(): a BROKEN symlink named .setpoint reports exists() == False,
    # so checking exists() alone lets the migration proceed into a collision.
    if new_dir.exists() or new_dir.is_symlink():
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

    # Body rewrites are non-recursive, and the guard above only inspects files
    # already IN that set — so a nested spec (".loom/sub/fleet.yaml" pointing at
    # "../alpha.loom.yaml") is invisible to both, and would survive the run with
    # its refs untouched while its targets were renamed out from under it.
    # Refuse rather than half-migrate.
    in_scope = {p.resolve() for p in rewrites}
    for p in sorted(spec_dir.rglob("*.yaml")):
        if p.resolve() in in_scope or not p.is_file():
            continue
        if _has_legacy_ref(p):
            rel = p.relative_to(spec_dir)
            problems.append(
                f"{rel} contains legacy references but is nested — this "
                f"migration only rewrites {LEGACY_DIR}/*.yaml")

    return MigrationPlan(repo=repo, spec_dir=spec_dir,
                         spec_renames=renames, body_rewrites=rewrites,
                         problems=problems)


def render_plan(plan: MigrationPlan) -> str:
    if plan.is_blocked:
        n = len(plan.problems)
        lines = [f"REFUSING — {n} problem{'' if n == 1 else 's'}:"]
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
        text = p.read_text()
        members = text.count(LEGACY_EXT)
        dir_refs = text.count(LEGACY_DIR_REF)
        if members:
            lines.append(f"  {p.name}: {members} member ref(s) rewritten")
        if dir_refs:
            lines.append(
                f"  {p.name}: {dir_refs} {LEGACY_DIR_REF} path ref(s) rewritten")
    lines.append("  not committed — review and commit yourself")
    lines.append(f"  note: tracked files move via 'git mv', which STAGES them —"
                 f" any uncommitted edits inside {LEGACY_DIR_REF} get staged too")
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
        # Extension first, then directory segment: a combined token like
        # ".loom/alpha.loom.yaml" needs both, and either order converges.
        p.write_text(p.read_text()
                     .replace(LEGACY_EXT, NEW_EXT)
                     .replace(LEGACY_DIR_REF, NEW_DIR_REF))
        actions.append(f"rewrote member refs in {p.name}")

    # 2. Spec files, still inside the legacy directory.
    for src, dst in plan.spec_renames:
        _move(plan.repo, src, dst)
        actions.append(f"{src.name} -> {dst.name}")

    # 3. The directory itself.
    _move(plan.repo, plan.spec_dir, plan.repo / NEW_DIR)
    actions.append(f"{LEGACY_DIR}/ -> {NEW_DIR}/")
    return actions

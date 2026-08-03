from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class Worktree:
    def __init__(self, repo: Path, branch: str):
        self.repo = Path(repo)
        self.branch = branch
        self.path: Path | None = None

    def create(self) -> Path:
        target = Path(tempfile.mkdtemp(prefix="setpoint-wt-"))
        # -B resets the branch if it already exists (resume-friendly)
        subprocess.run(
            ["git", "worktree", "add", "-B", self.branch, str(target)],
            cwd=self.repo, check=True, capture_output=True, text=True,
        )
        self.path = target
        return target

    def cleanup(self) -> None:
        if self.path is None:
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(self.path)],
            cwd=self.repo, capture_output=True, text=True,
        )
        self.path = None


def prepare_workspace(spec) -> tuple[Path, Worktree | None]:
    if spec.workspace.worktree:
        branch = spec.workspace.branch or f"setpoint/{spec.name}"
        wt = Worktree(repo=spec.workspace.repo, branch=branch)
        return wt.create(), wt
    return spec.workspace.repo, None

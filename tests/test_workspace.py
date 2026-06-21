import subprocess
from pathlib import Path

from loom.workspace import Worktree, prepare_workspace
from loom.spec import LoopSpec, Workspace, Context, ExecuteCfg, VerifyCfg, StopCfg, BudgetCfg


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _make_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("hi")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def test_worktree_create_and_cleanup(tmp_path):
    repo = _make_repo(tmp_path)
    wt = Worktree(repo=repo, branch="loom/test")
    path = wt.create()
    assert path.exists()
    assert (path / "f.txt").read_text() == "hi"
    assert path != repo
    wt.cleanup()
    assert not path.exists()


def test_prepare_workspace_no_worktree(tmp_path):
    repo = _make_repo(tmp_path)
    spec = LoopSpec(name="n", goal="g", type="coding",
                    workspace=Workspace(repo=repo, worktree=False, branch=None),
                    context=Context(), execute=ExecuteCfg(), verify=VerifyCfg(command="true"),
                    stop=StopCfg(), budget=BudgetCfg())
    cwd, wt = prepare_workspace(spec)
    assert cwd == repo
    assert wt is None

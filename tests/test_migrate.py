import subprocess
from pathlib import Path

import pytest

from setpoint.migrate import (MigrationPlan, apply_migration, plan_migration,
                              render_plan, _is_tracked)


def _repo(tmp_path, *, git=True, track=True) -> Path:
    repo = tmp_path / "r"
    (repo / ".loom").mkdir(parents=True)
    (repo / ".loom" / "alpha.loom.yaml").write_text("name: alpha\n")
    (repo / ".loom" / "beta.loom.yaml").write_text("name: beta\n")
    (repo / ".loom" / "fleet.yaml").write_text(
        "name: f\nmembers:\n  - alpha.loom.yaml\n  - beta.loom.yaml\n")
    if git:
        for a in (["init", "-q"], ["config", "user.email", "t@t"],
                  ["config", "user.name", "t"]):
            subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
        if track:
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-qm", "init"], cwd=repo,
                           check=True, capture_output=True)
    return repo


def test_plan_finds_specs_and_bodies(tmp_path):
    plan = plan_migration(_repo(tmp_path))
    assert plan.spec_dir.name == ".loom"
    assert sorted(p.name for p, _ in plan.spec_renames) == \
        ["alpha.loom.yaml", "beta.loom.yaml"]
    assert [p.name for p in plan.body_rewrites] == ["fleet.yaml"]


def test_plan_is_empty_when_no_loom_dir(tmp_path):
    repo = tmp_path / "clean"
    repo.mkdir()
    plan = plan_migration(repo)
    assert plan.spec_dir is None
    assert plan.spec_renames == [] and plan.body_rewrites == []


def test_render_plan_does_not_touch_disk(tmp_path):
    repo = _repo(tmp_path)
    out = render_plan(plan_migration(repo))
    assert ".setpoint" in out
    assert (repo / ".loom" / "alpha.loom.yaml").exists()  # unchanged


def test_apply_renames_dir_specs_and_bodies(tmp_path):
    repo = _repo(tmp_path)
    apply_migration(plan_migration(repo))

    assert not (repo / ".loom").exists()
    assert (repo / ".setpoint" / "alpha.setpoint.yaml").exists()
    assert (repo / ".setpoint" / "beta.setpoint.yaml").exists()

    # the critical case: fleet.yaml is NOT renamed but its body IS rewritten
    fleet = repo / ".setpoint" / "fleet.yaml"
    assert fleet.exists()
    assert "alpha.setpoint.yaml" in fleet.read_text()
    assert ".loom.yaml" not in fleet.read_text()


def test_apply_preserves_git_history_for_tracked_files(tmp_path):
    repo = _repo(tmp_path, git=True, track=True)
    apply_migration(plan_migration(repo))
    out = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                         capture_output=True, text=True).stdout
    assert "R " in out  # staged as renames, not delete+add


def test_apply_never_commits(tmp_path):
    repo = _repo(tmp_path, git=True, track=True)
    before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                            capture_output=True, text=True).stdout
    apply_migration(plan_migration(repo))
    after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                           capture_output=True, text=True).stdout
    assert before == after


def test_apply_works_without_git(tmp_path):
    repo = _repo(tmp_path, git=False)
    apply_migration(plan_migration(repo))
    assert (repo / ".setpoint" / "alpha.setpoint.yaml").exists()


def test_untracked_files_in_a_git_repo_use_plain_move(tmp_path):
    repo = _repo(tmp_path, git=True, track=False)
    assert not _is_tracked(repo, repo / ".loom" / "alpha.loom.yaml")
    apply_migration(plan_migration(repo))
    assert (repo / ".setpoint" / "alpha.setpoint.yaml").exists()

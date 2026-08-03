import subprocess
from pathlib import Path

import pytest

from setpoint.migrate import (MigrationBlocked, apply_migration,
                              plan_migration, render_plan, _is_tracked)


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


def test_setpoint_dir_already_exists_blocks_and_leaves_disk_unchanged(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".setpoint").mkdir()

    plan = plan_migration(repo)
    assert plan.is_blocked
    assert ".setpoint/ already exists" in plan.problems

    with pytest.raises(MigrationBlocked):
        apply_migration(plan)

    # nothing on disk changed
    assert (repo / ".loom" / "alpha.loom.yaml").read_text() == "name: alpha\n"
    assert (repo / ".loom" / "beta.loom.yaml").exists()
    assert (repo / ".loom" / "fleet.yaml").read_text() == (
        "name: f\nmembers:\n  - alpha.loom.yaml\n  - beta.loom.yaml\n")


def test_colliding_destination_blocks_and_preserves_destination_content(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "alpha.setpoint.yaml").write_text("name: pre-existing\n")

    plan = plan_migration(repo)
    assert plan.is_blocked
    assert "alpha.setpoint.yaml would be overwritten" in plan.problems

    with pytest.raises(MigrationBlocked):
        apply_migration(plan)

    # the destination's original content must survive untouched
    assert (repo / ".loom" / "alpha.setpoint.yaml").read_text() == "name: pre-existing\n"
    assert (repo / ".loom" / "alpha.loom.yaml").exists()


def test_fleet_reference_outside_rename_scope_blocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "sub").mkdir()
    (repo / ".loom" / "sub" / "x.loom.yaml").write_text("name: x\n")
    (repo / ".loom" / "fleet.yaml").write_text(
        "name: f\nmembers:\n  - alpha.loom.yaml\n  - sub/x.loom.yaml\n")

    plan = plan_migration(repo)
    assert plan.is_blocked
    assert any(
        "sub/x.loom.yaml" in problem and "will not rename" in problem
        for problem in plan.problems
    )

    with pytest.raises(MigrationBlocked):
        apply_migration(plan)
    assert (repo / ".loom" / "sub" / "x.loom.yaml").exists()
    assert "sub/x.loom.yaml" in (repo / ".loom" / "fleet.yaml").read_text()


def test_render_plan_shows_problems_when_blocked(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".setpoint").mkdir()

    out = render_plan(plan_migration(repo))
    assert "REFUSING" in out
    assert ".setpoint/ already exists" in out
    assert "nothing was changed" in out


def test_clean_repo_is_not_blocked(tmp_path):
    plan = plan_migration(_repo(tmp_path))
    assert not plan.is_blocked
    assert plan.problems == []


def test_apply_migration_return_value(tmp_path):
    repo = _repo(tmp_path)
    actions = apply_migration(plan_migration(repo))
    assert actions == [
        "rewrote member refs in fleet.yaml",
        "alpha.loom.yaml -> alpha.setpoint.yaml",
        "beta.loom.yaml -> beta.setpoint.yaml",
        ".loom/ -> .setpoint/",
    ]


# --- .loom/ directory references -------------------------------------------
# The directory is renamed too, so a reference to a NON-spec file inside it
# (rubric, script, corpus) dangles unless the body rewrite covers ".loom/".


def test_dir_ref_to_non_spec_file_is_rewritten(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "alpha.loom.yaml").write_text(
        "name: alpha\nverify:\n  rubric: .loom/rubric-truth.md\n")

    plan = plan_migration(repo)
    assert repo / ".loom" / "alpha.loom.yaml" in plan.body_rewrites

    apply_migration(plan)
    assert (repo / ".setpoint" / "alpha.setpoint.yaml").read_text() == \
        "name: alpha\nverify:\n  rubric: .setpoint/rubric-truth.md\n"


def test_body_with_both_member_ref_and_dir_ref_in_either_order(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "fleet.yaml").write_text(
        "rubric: .loom/before.md\n"          # dir ref BEFORE member refs
        "members:\n  - alpha.loom.yaml\n  - beta.loom.yaml\n"
        "corpus: .loom/after.txt\n")         # dir ref AFTER member refs

    apply_migration(plan_migration(repo))
    body = (repo / ".setpoint" / "fleet.yaml").read_text()
    assert body == (
        "rubric: .setpoint/before.md\n"
        "members:\n  - alpha.setpoint.yaml\n  - beta.setpoint.yaml\n"
        "corpus: .setpoint/after.txt\n")
    assert ".loom" not in body


def test_dash_loom_paths_are_not_false_positives(tmp_path):
    """`program-health-loom/` contains "-loom/", not ".loom/" — leave it be."""
    repo = _repo(tmp_path)
    # The "-loom/" text sits in a file that IS rewritten (it carries a real
    # legacy ref), so the replace genuinely runs over it.
    (repo / ".loom" / "fleet.yaml").write_text(
        "name: f\nmembers:\n  - alpha.loom.yaml\n"
        "  repo: /Users/jeff/workspace/program-health-loom\n"
        "  sub: /Users/jeff/workspace/program-health-loom/specs\n"
        "  odd: /tmp/-loom/thing\n")

    plan = plan_migration(repo)
    assert repo / ".loom" / "fleet.yaml" in plan.body_rewrites  # replace runs
    apply_migration(plan)

    body = (repo / ".setpoint" / "fleet.yaml").read_text()
    assert "  repo: /Users/jeff/workspace/program-health-loom\n" in body
    assert "  sub: /Users/jeff/workspace/program-health-loom/specs\n" in body
    assert "  odd: /tmp/-loom/thing\n" in body
    assert "program-health-setpoint" not in body
    assert "alpha.setpoint.yaml" in body  # the real ref still got rewritten


def test_render_plan_reports_directory_ref_rewrites(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "alpha.loom.yaml").write_text(
        "name: alpha\nrubric: .loom/r.md\ncorpus: .loom/c.txt\n")

    out = render_plan(plan_migration(repo))
    assert "alpha.loom.yaml: 2 .loom/ path ref(s) rewritten" in out


# --- nested specs ----------------------------------------------------------
# Body rewrites are non-recursive; anything nested must BLOCK rather than
# half-migrate (owner ruling: refuse rather than half-migrate).


def test_nested_yaml_with_legacy_member_ref_blocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "sub").mkdir()
    (repo / ".loom" / "sub" / "fleet.yaml").write_text(
        "name: nested\nmembers:\n  - ../alpha.loom.yaml\n")

    plan = plan_migration(repo)
    assert plan.is_blocked
    assert any("sub/fleet.yaml" in problem for problem in plan.problems)

    with pytest.raises(MigrationBlocked):
        apply_migration(plan)

    # filesystem completely unchanged
    assert not (repo / ".setpoint").exists()
    assert (repo / ".loom" / "alpha.loom.yaml").exists()
    assert (repo / ".loom" / "sub" / "fleet.yaml").read_text() == \
        "name: nested\nmembers:\n  - ../alpha.loom.yaml\n"


def test_nested_yaml_with_legacy_dir_ref_blocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "sub").mkdir()
    (repo / ".loom" / "sub" / "child.yaml").write_text("rubric: .loom/r.md\n")

    plan = plan_migration(repo)
    assert plan.is_blocked
    assert any("sub/child.yaml" in problem for problem in plan.problems)

    with pytest.raises(MigrationBlocked):
        apply_migration(plan)
    assert not (repo / ".setpoint").exists()


def test_nested_yaml_without_legacy_refs_does_not_block(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".loom" / "sub").mkdir()
    (repo / ".loom" / "sub" / "notes.yaml").write_text("name: unrelated\n")

    plan = plan_migration(repo)
    assert not plan.is_blocked
    apply_migration(plan)
    assert (repo / ".setpoint" / "sub" / "notes.yaml").exists()


# --- one-liners ------------------------------------------------------------


def test_broken_symlink_at_destination_blocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".setpoint").symlink_to(tmp_path / "does-not-exist")

    plan = plan_migration(repo)
    assert plan.is_blocked
    assert ".setpoint/ already exists" in plan.problems

    with pytest.raises(MigrationBlocked):
        apply_migration(plan)
    assert (repo / ".loom" / "alpha.loom.yaml").exists()


def test_single_problem_is_not_pluralized(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".setpoint").mkdir()

    out = render_plan(plan_migration(repo))
    assert "1 problem:" in out
    assert "1 problems" not in out


def test_render_plan_warns_that_git_mv_stages(tmp_path):
    out = render_plan(plan_migration(_repo(tmp_path)))
    assert "stage" in out.lower()

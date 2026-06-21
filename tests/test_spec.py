import pytest
from loom.spec import load_spec


def test_load_coding_spec():
    s = load_spec("tests/fixtures/coding.yaml")
    assert s.name == "demo-coding"
    assert s.type == "coding"
    assert s.workspace.worktree is True
    assert s.workspace.branch == "loom/demo"
    assert s.context.files == ["VISION.md"]
    assert s.execute.plan_model == "deepseek-v4-pro"
    assert s.execute.model == "deepseek-v4-flash"
    assert s.verify.gate == "command"
    assert s.verify.command == "pytest -q"
    assert s.stop.max_iters == 5
    assert s.stop.no_progress_after == 2
    assert s.budget.max_usd == 1.5


def test_rejects_unknown_type(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("name: x\ngoal: g\ntype: nope\nworkspace:\n  repo: /tmp\n")
    with pytest.raises(ValueError, match="type must be"):
        load_spec(str(p))


def test_judge_gate_defaults(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "name: x\ngoal: g\ntype: content\n"
        "workspace:\n  repo: /tmp\n"
        "verify:\n  gate: judge\n  rubric: r.md\n"
    )
    s = load_spec(str(p))
    assert s.verify.judge_model == "gpt-oss-20b"
    assert s.verify.pass_threshold == 0.8
    assert s.workspace.worktree is False  # default


def test_judge_model_must_differ_from_execute_model(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "name: x\ngoal: g\ntype: content\n"
        "workspace:\n  repo: /tmp\n"
        "execute:\n  model: deepseek-v4-flash\n"
        "verify:\n  gate: judge\n  rubric: r.md\n  judge_model: deepseek-v4-flash\n"
    )
    import pytest
    with pytest.raises(ValueError, match="maker != checker"):
        load_spec(str(p))


def test_load_spec_expands_tilde_in_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    spec_file = tmp_path / "s.yaml"
    spec_file.write_text(
        "name: x\ngoal: g\ntype: coding\n"
        "workspace:\n  repo: /tmp\n"
        "verify:\n  gate: command\n  command: 'true'\n"
    )
    s = load_spec("~/s.yaml")
    assert s.name == "x"

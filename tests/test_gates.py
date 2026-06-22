from types import SimpleNamespace

from loom.gates import GateResult
from loom.gates.command import CommandGate
from loom.gates.judge import JudgeGate


def test_command_gate_pass(tmp_path):
    g = CommandGate(command="true")
    r = g.verify(cwd=tmp_path, on_event=lambda e: None)
    assert isinstance(r, GateResult)
    assert r.passed is True


def test_command_gate_fail_captures_output(tmp_path):
    g = CommandGate(command="echo boom >&2; exit 1")
    r = g.verify(cwd=tmp_path, on_event=lambda e: None)
    assert r.passed is False
    assert "boom" in r.feedback


def test_judge_gate_parses_score(tmp_path):
    artifact = tmp_path / "brief.md"
    artifact.write_text("a draft")

    def fake_create(**kw):
        content = '{"score": 0.9, "feedback": "great"}'
        msg = SimpleNamespace(content=content)
        usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    g = JudgeGate(client=client, model="gpt-oss-20b",
                  rubric_text="be good", threshold=0.8, artifact=str(artifact))
    r = g.verify(cwd=tmp_path, on_event=lambda e: None)
    assert r.passed is True
    assert r.score == 0.9


def test_judge_gate_fail_below_threshold(tmp_path):
    artifact = tmp_path / "brief.md"
    artifact.write_text("weak")

    def fake_create(**kw):
        msg = SimpleNamespace(content='{"score": 0.4, "feedback": "thin"}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    g = JudgeGate(client=client, model="gpt-oss-20b",
                  rubric_text="r", threshold=0.8, artifact=str(artifact))
    r = g.verify(cwd=tmp_path, on_event=lambda e: None)
    assert r.passed is False
    assert "thin" in r.feedback


def test_build_gate_local_judge_disables_thinking(tmp_path):
    from loom.spec import load_spec
    from loom.gates import build_gate
    rubric = tmp_path / "r.md"
    rubric.write_text("be good")
    spec_file = tmp_path / "c.yaml"
    spec_file.write_text(
        f"name: x\ngoal: g\ntype: content\n"
        f"workspace:\n  repo: {tmp_path}\n"
        f"execute:\n  model: deepseek-v4-flash\n"
        f"verify:\n  gate: judge\n  rubric: {rubric}\n  judge_model: qwen3.6:27b\n"
    )
    spec = load_spec(str(spec_file))
    gate = build_gate(spec, judge_client=object())
    assert gate.extra_body == {"reasoning_effort": "none"}


def test_build_gate_deepseek_judge_no_extra_body(tmp_path):
    from loom.spec import load_spec
    from loom.gates import build_gate
    rubric = tmp_path / "r.md"
    rubric.write_text("be good")
    spec_file = tmp_path / "c.yaml"
    spec_file.write_text(
        f"name: x\ngoal: g\ntype: content\n"
        f"workspace:\n  repo: {tmp_path}\n"
        f"execute:\n  model: deepseek-v4-flash\n"
        f"verify:\n  gate: judge\n  rubric: {rubric}\n  judge_model: deepseek-v4-pro\n"
    )
    spec = load_spec(str(spec_file))
    gate = build_gate(spec, judge_client=object())
    assert gate.extra_body is None

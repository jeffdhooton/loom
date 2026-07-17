from __future__ import annotations

import json
from pathlib import Path


class _FakeCompleted:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_agent_judge_client_shape(monkeypatch):
    import subprocess
    from loom.gates.agent_judge import AgentJudgeClient
    verdict = {"criteria": [{"name": "works", "pass": True, "evidence": "tests pass"}],
               "score": 0.95, "feedback": "ok"}
    captured = {}

    def fake_run(argv, **kwargs):
        captured["stdin"] = kwargs.get("stdin")
        return _FakeCompleted(0, json.dumps(verdict))

    client = AgentJudgeClient(engine="claude", runner=fake_run)
    resp = client.chat.completions.create(
        model="claude", messages=[{"role": "user", "content": "grade this"}],
        extra_body={"reasoning_effort": "none"})  # extra kwargs ignored, not passed to CLI
    assert json.loads(resp.choices[0].message.content)["score"] == 0.95
    # the grader must never block reading stdin on an unattended run
    assert captured["stdin"] == subprocess.DEVNULL


def test_agent_judge_client_missing_binary_fails_closed():
    from loom.gates.agent_judge import AgentJudgeClient

    def fake_run(argv, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    client = AgentJudgeClient(engine="claude", runner=fake_run)
    resp = client.chat.completions.create(
        model="claude", messages=[{"role": "user", "content": "grade this"}])
    assert resp.choices[0].message.content == "{}"


def test_make_judge_client_dispatches_to_agent(monkeypatch):
    from loom.clients import make_judge_client
    from loom.gates.agent_judge import AgentJudgeClient
    client = make_judge_client("claude", engine="claude")
    assert isinstance(client, AgentJudgeClient)


def test_judge_gate_reads_git_diff_artifact(monkeypatch, tmp_path):
    from loom.gates.judge import JudgeGate

    def fake_run(argv, **kwargs):
        assert argv[:2] == ["git", "diff"]
        return _FakeCompleted(0, "diff --git a/x b/x\n+added line")

    monkeypatch.setattr("loom.gates.judge.subprocess.run", fake_run)
    gate = JudgeGate(client=None, model="claude", rubric_text="r", threshold=0.8,
                     artifact="@diff")
    text = gate._read_artifact(tmp_path)
    assert "added line" in text

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import loom.__main__ as cli
from loom.executor.base import ExecuteResult
from loom.budget import Usage


def _make_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for a in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
    # a failing test that passes once marker file exists
    (repo / "check.sh").write_text('test -f PASS')
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def test_cmd_run_converges(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    spec = tmp_path / "loop.yaml"
    spec.write_text(
        f"name: cli-demo\ngoal: make check pass\ntype: coding\n"
        f"workspace:\n  repo: {repo}\n  worktree: false\n"
        f"execute:\n  tools: [write]\n"
        f"verify:\n  gate: command\n  command: 'sh check.sh'\n"
        f"stop:\n  max_iters: 3\nbudget:\n  max_usd: 5.0\n")

    # Executor that creates the PASS marker so the command gate flips to green.
    class WinningExecutor:
        def execute(self, system, task, tools, model, cwd, on_event):
            (Path(cwd) / "PASS").write_text("")
            return ExecuteResult(text="created PASS", usage=Usage(100, 50, 0))

    monkeypatch.setattr(cli, "_build_executor", lambda spec: WinningExecutor())
    monkeypatch.setattr(cli, "_build_plan_client",
                        lambda spec: _fake_plan_client())
    monkeypatch.setenv("LOOM_RUNS_ROOT", str(tmp_path / "runs"))

    rc = cli.main(["run", str(spec)])
    assert rc == 0
    state = json.loads((tmp_path / "runs" / "cli-demo" / "state.json").read_text())
    assert state["status"] == "passed"


def _fake_plan_client():
    def create(**kw):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="plan: touch PASS"))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, prompt_cache_hit_tokens=0))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_ls_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOOM_RUNS_ROOT", str(tmp_path / "runs"))
    assert cli.main(["ls"]) == 0


def test_build_executor_selects_engine(tmp_path, monkeypatch):
    from loom import __main__ as m
    from loom.executor import ClaudeExecutor, CodexExecutor, DeepSeekExecutor
    from loom.executor.agent_plan import AgentPlanClient

    def spec_with(engine):
        from loom.spec import ExecuteCfg
        class S:  # minimal stand-in
            execute = ExecuteCfg(engine=engine)
        return S()

    # DeepSeek path must not require a real key for this unit test:
    monkeypatch.setattr(m, "make_deepseek_client", lambda: object(), raising=False)

    assert isinstance(m._build_executor(spec_with("claude")), ClaudeExecutor)
    assert isinstance(m._build_executor(spec_with("codex")), CodexExecutor)
    assert isinstance(m._build_plan_client(spec_with("claude")), AgentPlanClient)

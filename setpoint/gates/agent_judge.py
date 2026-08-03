from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Response:
    choices: list


def _prompt_from_messages(messages) -> str:
    return "\n\n".join(m.get("content", "") for m in (messages or []) if m.get("content"))


class _Completions:
    def __init__(self, engine: str, runner, timeout: int):
        self.engine = engine
        self.runner = runner
        self.timeout = timeout

    def create(self, model=None, messages=None, **kwargs):
        prompt = _prompt_from_messages(messages)
        if self.engine == "claude":
            argv = ["claude", "-p", prompt, "--output-format", "text",
                    "--permission-mode", "plan"]  # read-only: grader must not edit
        else:  # codex
            argv = ["codex", "exec", "--sandbox", "read-only", prompt]
        try:
            proc = self.runner(argv, capture_output=True, text=True,
                               timeout=self.timeout, stdin=subprocess.DEVNULL)
            content = (proc.stdout or "").strip() if proc.returncode == 0 else "{}"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            content = "{}"
        return _Response(choices=[_Choice(_Message(content))])


class _Chat:
    def __init__(self, engine, runner, timeout):
        self.completions = _Completions(engine, runner, timeout)


class AgentJudgeClient:
    """OpenAI-shaped client that runs a fresh Claude/Codex agent as the checker.
    Read-only: the grader inspects, it does not edit. Returns the agent's stdout
    as .choices[0].message.content so the existing JudgeGate parses it unchanged."""

    def __init__(self, engine: str, runner=subprocess.run, timeout: int = 900):
        self.chat = _Chat(engine, runner, timeout)

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class GateResult:
    passed: bool
    feedback: str
    score: float | None = None


class Gate(abc.ABC):
    @abc.abstractmethod
    def verify(self, cwd: Path, on_event: Callable) -> GateResult:
        ...


def build_gate(spec, judge_client=None) -> Gate:
    from .command import CommandGate
    from .judge import JudgeGate

    if spec.verify.gate == "command":
        return CommandGate(command=spec.verify.command)
    rubric_text = Path(spec.verify.rubric).expanduser().read_text()
    artifact = spec.deliver.get("artifact") if spec.deliver else None
    judge_model = spec.verify.judge_model
    extra_body = None if judge_model.startswith("deepseek") else {"reasoning_effort": "none"}
    return JudgeGate(client=judge_client, model=judge_model,
                     rubric_text=rubric_text, threshold=spec.verify.pass_threshold,
                     artifact=artifact, extra_body=extra_body,
                     checks=spec.verify.checks)

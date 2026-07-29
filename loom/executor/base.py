from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from loom.budget import Usage
from loom.tools import Tool


@dataclass
class ExecEvent:
    kind: str  # "tool" | "assistant" | "note"
    data: dict


@dataclass
class ExecuteResult:
    text: str
    usage: Usage
    steps: list[dict] = field(default_factory=list)


class Executor(abc.ABC):
    def set_deadline(self, remaining_secs: float | None) -> None:
        """Wall-clock seconds left in the run budget; executors that shell out
        clamp their subprocess timeout to it so one turn can't overshoot."""

    @abc.abstractmethod
    def execute(self, system: str, task: str, tools: list[Tool], model: str,
                cwd: Path, on_event: Callable[[ExecEvent], None]) -> ExecuteResult:
        ...

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from . import Gate, GateResult

_MAX = 6000


class CommandGate(Gate):
    def __init__(self, command: str):
        self.command = command

    def verify(self, cwd: Path, on_event: Callable) -> GateResult:
        on_event({"kind": "verify_start", "command": self.command})
        proc = subprocess.run(self.command, shell=True, cwd=cwd,
                              capture_output=True, text=True)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if len(out) > _MAX:
            out = out[:_MAX] + "\n…[truncated]"
        passed = proc.returncode == 0
        feedback = out if not passed else "all checks passed"
        return GateResult(passed=passed, feedback=feedback or f"exit {proc.returncode}")

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class IterRecord:
    n: int
    plan: str
    summary: str
    passed: bool
    feedback: str
    usd: float
    score: float | None = None


@dataclass
class RunState:
    name: str
    status: str = "new"  # new | running | passed | stopped | budget_exhausted
    iters: list[IterRecord] = field(default_factory=list)
    spent_usd: float = 0.0


class Memory:
    def __init__(self, name: str, root: Path | None = None):
        self.name = name
        self.root = (root or (Path.home() / ".loom" / "runs")) / name
        self.state_path = self.root / "state.json"
        self.log_path = self.root / "log.md"

    def start(self) -> RunState:
        self.root.mkdir(parents=True, exist_ok=True)
        state = self.load()
        if state.status == "new":
            state.status = "running"
            self._write(state)
        return state

    def load(self) -> RunState:
        if not self.state_path.exists():
            return RunState(name=self.name)
        raw = json.loads(self.state_path.read_text())
        return RunState(
            name=raw["name"],
            status=raw.get("status", "new"),
            iters=[IterRecord(**r) for r in raw.get("iters", [])],
            spent_usd=raw.get("spent_usd", 0.0),
        )

    def append(self, rec: IterRecord) -> None:
        state = self.load()
        state.iters.append(rec)
        state.spent_usd += rec.usd
        self._write(state)
        self._append_log(rec)

    def set_status(self, status: str) -> None:
        state = self.load()
        state.status = status
        self._write(state)

    def context_block(self) -> str:
        state = self.load()
        if not state.iters:
            return "No previous iterations."
        lines = ["## Loop history (memory spine)"]
        for r in state.iters:
            verdict = "PASS" if r.passed else "FAIL"
            lines.append(f"- iteration {r.n} [{verdict}]: {r.summary}")
            if not r.passed and r.feedback:
                lines.append(f"  feedback: {r.feedback}")
        return "\n".join(lines)

    def _write(self, state: RunState) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2))
        tmp.replace(self.state_path)  # atomic

    def _append_log(self, rec: IterRecord) -> None:
        verdict = "✅ PASS" if rec.passed else "❌ FAIL"
        block = (
            f"\n## Iteration {rec.n} — {verdict} (${rec.usd:.4f})\n\n"
            f"**Plan:** {rec.plan}\n\n"
            f"**Did:** {rec.summary}\n\n"
            f"**Verify:** {rec.feedback}\n"
        )
        with self.log_path.open("a") as f:
            f.write(block)

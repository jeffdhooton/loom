from __future__ import annotations

from rich.console import Console

from loom.budget import Budget
from loom.gates import GateResult
from loom.memory import RunState


class StreamUI:
    def __init__(self, name: str, budget: Budget):
        self.name = name
        self.budget = budget
        self.console = Console()

    def _budget_str(self) -> str:
        spent = self.budget.spent_usd
        s = f"${spent:.4f}" if spent < 1 else f"${spent:.2f}"
        if self.budget.max_usd is not None:
            return f"{s}/${self.budget.max_usd:.2f}"
        return s

    def header(self, **kw) -> None:
        self.console.rule(f"[bold]loom ▸ {self.name}[/bold]")

    def stage(self, name: str, n: int, total: int) -> None:
        warn = " [yellow](budget 80%)[/yellow]" if self.budget.warn() else ""
        self.console.print(
            f"[dim]iter {n}/{total} │ {self._budget_str()} │[/dim] [bold cyan]{name}[/bold cyan]{warn}")

    def tool(self, name: str, args: dict) -> None:
        preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in (args or {}).items())
        self.console.print(f"  [dim]→ {name}({preview})[/dim]")

    def verify(self, result: GateResult) -> None:
        if result.passed:
            self.console.print("  [bold green]✓ VERIFY passed[/bold green]")
        else:
            score = f" (score {result.score})" if result.score is not None else ""
            self.console.print(f"  [bold red]✗ VERIFY failed{score}[/bold red]: {result.feedback[:200]}")

    def summary(self, state: RunState) -> None:
        color = "green" if state.status == "passed" else "yellow"
        self.console.rule(f"[{color}]{self.name}: {state.status}[/{color}]")
        self.console.print(
            f"iterations: {len(state.iters)} │ spent: ${state.spent_usd:.2f}")


class NullUI:
    """A silent UI for fleet members — progress lives in each run's state.json
    and log.md, not interleaved on a shared stdout."""

    def header(self, *a, **k) -> None: ...
    def stage(self, *a, **k) -> None: ...
    def tool(self, *a, **k) -> None: ...
    def verify(self, *a, **k) -> None: ...
    def summary(self, *a, **k) -> None: ...

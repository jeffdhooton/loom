from pathlib import Path
from types import SimpleNamespace

from loom.cycle import Cycle
from loom.spec import LoopSpec, Workspace, Context, ExecuteCfg, VerifyCfg, StopCfg, BudgetCfg
from loom.budget import Budget, Usage, PRICING
from loom.memory import Memory
from loom.gates import GateResult
from loom.executor.base import ExecuteResult


class StubUI:
    def __init__(self): self.events = []
    def stage(self, name, n, total): self.events.append(("stage", name, n))
    def tool(self, name, args): pass
    def verify(self, result): self.events.append(("verify", result.passed))
    def header(self, **kw): pass
    def summary(self, state): self.events.append(("summary", state.status))


class FakeExecutor:
    def __init__(self, usage_per=Usage(1000, 500, 0)):
        self.usage_per = usage_per
        self.calls = 0
    def execute(self, system, task, tools, model, cwd, on_event):
        self.calls += 1
        return ExecuteResult(text=f"did work {self.calls}", usage=self.usage_per)


class FakeGate:
    def __init__(self, pass_on_iter):
        self.pass_on_iter = pass_on_iter
        self.calls = 0
    def verify(self, cwd, on_event):
        self.calls += 1
        passed = self.calls >= self.pass_on_iter
        return GateResult(passed=passed, feedback="ok" if passed else "still failing")


def _plan_client(text="here is the plan"):
    def create(**kw):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5,
                                  prompt_cache_hit_tokens=0))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _spec(tmp_path, max_iters=5, no_progress=None):
    return LoopSpec(name="t", goal="make it green", type="coding",
                    workspace=Workspace(repo=tmp_path, worktree=False, branch=None),
                    context=Context(notes="n"), execute=ExecuteCfg(tools=["read"]),
                    verify=VerifyCfg(command="true"),
                    stop=StopCfg(max_iters=max_iters, no_progress_after=no_progress),
                    budget=BudgetCfg(max_usd=10.0))


def test_cycle_stops_on_pass(tmp_path):
    spec = _spec(tmp_path)
    ex, gate, ui = FakeExecutor(), FakeGate(pass_on_iter=3), StubUI()
    mem = Memory("t", root=tmp_path / "runs")
    cyc = Cycle(spec, ex, gate, mem, Budget(10.0, None, PRICING), ui, _plan_client())
    state = cyc.run(cwd=tmp_path)
    assert state.status == "passed"
    assert len(state.iters) == 3
    assert ex.calls == 3


def test_cycle_stops_on_max_iters(tmp_path):
    spec = _spec(tmp_path, max_iters=2)
    ex, gate = FakeExecutor(), FakeGate(pass_on_iter=99)
    cyc = Cycle(spec, ex, gate, Memory("t", root=tmp_path / "r"),
                Budget(10.0, None, PRICING), StubUI(), _plan_client())
    state = cyc.run(cwd=tmp_path)
    assert state.status == "stopped"
    assert len(state.iters) == 2


def test_cycle_stops_on_budget(tmp_path):
    spec = _spec(tmp_path, max_iters=99)
    # each iter costs pro-rate; cap forces stop after ~1-2 iters
    ex = FakeExecutor(usage_per=Usage(1_000_000, 1_000_000, 0))  # ~$0.42 flash/iter
    cyc = Cycle(spec, ex, FakeGate(pass_on_iter=99),
                Memory("t", root=tmp_path / "r"),
                Budget(0.50, None, PRICING), StubUI(), _plan_client())
    state = cyc.run(cwd=tmp_path)
    assert state.status == "budget_exhausted"


def test_cycle_resume_continues_iter_numbering(tmp_path):
    # A resume (second run on the same memory) must continue the iteration labels
    # rather than restarting at 1 — so the spine reads 1,2,3,4 not 1,2,1,2.
    spec = _spec(tmp_path, max_iters=2)
    mem = Memory("t", root=tmp_path / "r")
    Cycle(spec, FakeExecutor(), FakeGate(pass_on_iter=99), mem,
          Budget(10.0, None, PRICING), StubUI(), _plan_client()).run(cwd=tmp_path)
    Cycle(spec, FakeExecutor(), FakeGate(pass_on_iter=99), mem,
          Budget(10.0, None, PRICING), StubUI(), _plan_client()).run(cwd=tmp_path)
    state = mem.load()
    assert [r.n for r in state.iters] == [1, 2, 3, 4]


def test_cycle_no_progress_bailout(tmp_path):
    spec = _spec(tmp_path, max_iters=99, no_progress=3)
    cyc = Cycle(spec, FakeExecutor(), FakeGate(pass_on_iter=99),
                Memory("t", root=tmp_path / "r"),
                Budget(100.0, None, PRICING), StubUI(), _plan_client())
    state = cyc.run(cwd=tmp_path)
    assert state.status == "stopped"
    assert len(state.iters) == 3  # bailed after 3 no-progress iters

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


def test_cycle_aborts_when_abort_check_true(tmp_path, monkeypatch):
    # A cycle whose abort_check() is True stops immediately with status "stopped".
    from types import SimpleNamespace
    from loom.cycle import Cycle
    from loom.memory import Memory
    from loom.budget import Budget, PRICING

    class _Gate:
        def verify(self, cwd, on_event):  # never reached
            from loom.gates import GateResult
            return GateResult(passed=True, feedback="", score=1.0)

    class _Exec:
        def execute(self, **kw):
            from loom.budget import Usage
            from loom.executor.base import ExecuteResult
            return ExecuteResult(text="", usage=Usage(), steps=[])

    class _UI:
        def stage(self, *a): ...
        def tool(self, *a): ...
        def verify(self, *a): ...
        def header(self, *a): ...
        def summary(self, *a): ...

    spec = SimpleNamespace(
        name="ab", goal="g",
        context=SimpleNamespace(notes="", files=[], scry=False),
        execute=SimpleNamespace(plan_model="m", model="m", engine="claude",
                                tools=["read"]),
        stop=SimpleNamespace(max_iters=5, no_progress_after=None),
        workspace=SimpleNamespace(repo=tmp_path),
    )
    from loom.executor.agent_plan import AgentPlanClient
    mem = Memory("ab", root=tmp_path / "runs")
    budget = Budget(None, None, PRICING)
    cyc = Cycle(spec, _Exec(), _Gate(), mem, budget, _UI(), AgentPlanClient(),
                abort_check=lambda: True)
    state = cyc.run(cwd=tmp_path)
    assert state.status == "stopped"
    assert len(state.iters) == 0


class UnrunnableGate:
    # exit 127: the verify command itself cannot run — not self-contained.
    supports_preflight = True

    def __init__(self):
        self.calls = 0

    def verify(self, cwd, on_event):
        self.calls += 1
        return GateResult(passed=False,
                          feedback="sh: demo:verify: command not found",
                          returncode=127)


def test_preflight_aborts_on_unrunnable_gate(tmp_path):
    ex = FakeExecutor()
    cyc = Cycle(_spec(tmp_path), ex, UnrunnableGate(), Memory("t", root=tmp_path / "r"),
                Budget(10.0, None, PRICING), StubUI(), _plan_client())
    state = cyc.run(cwd=tmp_path)
    assert state.status == "gate_error"
    assert ex.calls == 0  # no iterations burned on a gate that can never pass


def test_preflight_respects_spec_opt_out(tmp_path):
    spec = _spec(tmp_path, max_iters=2)
    spec.verify.preflight = False
    gate = UnrunnableGate()
    state = Cycle(spec, FakeExecutor(), gate, Memory("t", root=tmp_path / "r"),
                  Budget(10.0, None, PRICING), StubUI(), _plan_client()).run(cwd=tmp_path)
    assert state.status != "gate_error"
    assert gate.calls == 2  # ran as normal iterations only


def test_preflight_cold_feedback_seeds_first_plan(tmp_path):
    prompts = []

    def create(**kw):
        prompts.append(kw["messages"][0]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="plan"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1,
                                  prompt_cache_hit_tokens=0))

    plan_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    class ColdFailGate:
        supports_preflight = True

        def __init__(self):
            self.calls = 0

        def verify(self, cwd, on_event):
            self.calls += 1
            if self.calls == 1:  # the cold preflight run
                return GateResult(passed=False, feedback="ECONNREFUSED :5290",
                                  returncode=1)
            return GateResult(passed=True, feedback="ok", returncode=0)

    cyc = Cycle(_spec(tmp_path), FakeExecutor(), ColdFailGate(),
                Memory("t", root=tmp_path / "r"), Budget(10.0, None, PRICING),
                StubUI(), plan_client)
    state = cyc.run(cwd=tmp_path)
    assert state.status == "passed"
    assert "ECONNREFUSED" in prompts[0]  # iter-1 plan already sees the cold failure


def test_cutoff_executor_warns_the_next_plan(tmp_path):
    # An EXECUTE that ran out of tool turns leaves half-finished work. The next
    # PLAN must be told, or it reads the gate failure as "wrong approach" and
    # rewrites working code.
    prompts = []

    def create(**kw):
        prompts.append(kw["messages"][0]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="plan"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1,
                                  prompt_cache_hit_tokens=0))

    plan_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    class CutOffExecutor(FakeExecutor):
        def execute(self, system, task, tools, model, cwd, on_event):
            self.calls += 1
            return ExecuteResult(text="[hit max tool turns]", usage=self.usage_per,
                                 stop_reason="max_turns")

    mem = Memory("t", root=tmp_path / "r")
    state = Cycle(_spec(tmp_path, max_iters=2), CutOffExecutor(),
                  FakeGate(pass_on_iter=99), mem,
                  Budget(10.0, None, PRICING), StubUI(), plan_client).run(cwd=tmp_path)

    assert "cut off" in prompts[1].lower()      # iter 2's plan sees it
    assert "max_turns" in prompts[1]
    assert "cut off" not in prompts[0].lower()  # iter 1 had no prior iteration
    assert state.iters[0].stop_reason == "max_turns"  # and it persists to state.json


def test_clean_executor_adds_no_cutoff_note(tmp_path):
    prompts = []

    def create(**kw):
        prompts.append(kw["messages"][0]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="plan"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1,
                                  prompt_cache_hit_tokens=0))

    plan_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    Cycle(_spec(tmp_path, max_iters=2), FakeExecutor(), FakeGate(pass_on_iter=99),
          Memory("t", root=tmp_path / "r"), Budget(10.0, None, PRICING),
          StubUI(), plan_client).run(cwd=tmp_path)
    assert all("cut off" not in p.lower() for p in prompts)


def test_cycle_retries_transient_plan_errors(tmp_path, monkeypatch):
    from loom import retry
    monkeypatch.setattr(retry, "_sleep", lambda s: None)

    class Transient(Exception):
        status_code = 503

    attempts = []

    def create(**kw):
        attempts.append(1)
        if len(attempts) < 3:
            raise Transient()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="plan"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1,
                                  prompt_cache_hit_tokens=0))

    plan_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    state = Cycle(_spec(tmp_path, max_iters=1), FakeExecutor(), FakeGate(pass_on_iter=1),
                  Memory("t", root=tmp_path / "r"), Budget(10.0, None, PRICING),
                  StubUI(), plan_client).run(cwd=tmp_path)

    assert state.status == "passed"  # a 503 blip no longer kills the run
    assert len(attempts) == 3


def test_cycle_passes_wall_clock_deadline_to_executor(tmp_path):
    class DeadlineExec(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.deadlines = []

        def set_deadline(self, remaining):
            self.deadlines.append(remaining)

    ex = DeadlineExec()
    cyc = Cycle(_spec(tmp_path, max_iters=1), ex, FakeGate(pass_on_iter=1),
                Memory("t", root=tmp_path / "r"),
                Budget(None, None, PRICING, wall_clock_secs=100), StubUI(), _plan_client())
    cyc.run(cwd=tmp_path)
    assert len(ex.deadlines) == 1
    assert ex.deadlines[0] is not None and 0 < ex.deadlines[0] <= 100

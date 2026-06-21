from loom.ui import StreamUI
from loom.budget import Budget, PRICING
from loom.memory import RunState, IterRecord
from loom.gates import GateResult


def test_ui_renders_without_error(capsys):
    ui = StreamUI(name="demo", budget=Budget(2.0, None, PRICING))
    ui.stage("EXECUTE", 2, 8)
    ui.tool("bash", {"cmd": "pytest"})
    ui.verify(GateResult(passed=False, feedback="1 failed"))
    ui.verify(GateResult(passed=True, feedback="ok"))
    state = RunState(name="demo", status="passed",
                     iters=[IterRecord(1, "p", "s", True, "ok", 0.12, None)],
                     spent_usd=0.12)
    ui.summary(state)
    out = capsys.readouterr().out
    assert "EXECUTE" in out
    assert "demo" in out
    assert "passed" in out.lower()

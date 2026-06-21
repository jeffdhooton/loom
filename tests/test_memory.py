from loom.memory import Memory, IterRecord, RunState


def test_append_load_roundtrip(tmp_path):
    m = Memory("demo", root=tmp_path)
    m.start()
    m.append(IterRecord(n=1, plan="do X", summary="did X", passed=False,
                         feedback="test failed", usd=0.10, score=None))
    m.append(IterRecord(n=2, plan="fix X", summary="fixed X", passed=True,
                        feedback="all green", usd=0.05, score=None))

    loaded = Memory("demo", root=tmp_path).load()
    assert isinstance(loaded, RunState)
    assert loaded.name == "demo"
    assert len(loaded.iters) == 2
    assert loaded.iters[1].passed is True
    assert round(loaded.spent_usd, 2) == 0.15


def test_context_block_includes_history(tmp_path):
    m = Memory("demo", root=tmp_path)
    m.start()
    m.append(IterRecord(1, "plan a", "summary a", False, "lint error on line 4", 0.01, None))
    block = m.context_block()
    assert "iteration 1" in block.lower()
    assert "lint error on line 4" in block


def test_load_missing_returns_fresh(tmp_path):
    state = Memory("never", root=tmp_path).load()
    assert state.iters == []
    assert state.status == "new"

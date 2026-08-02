import pytest
from setpoint.tools import build_registry, ToolContext


def reg_map(names):
    return {t.name: t for t in build_registry(names)}


def test_write_then_read(tmp_path):
    ctx = ToolContext(cwd=tmp_path)
    tools = reg_map(["read", "write"])
    tools["write"].run({"path": "a.txt", "content": "hello"}, ctx)
    assert (tmp_path / "a.txt").read_text() == "hello"
    assert tools["read"].run({"path": "a.txt"}, ctx) == "hello"


def test_edit_replaces_unique(tmp_path):
    ctx = ToolContext(cwd=tmp_path)
    (tmp_path / "b.txt").write_text("foo BAR baz")
    out = reg_map(["edit"])["edit"].run(
        {"path": "b.txt", "old": "BAR", "new": "QUX"}, ctx)
    assert (tmp_path / "b.txt").read_text() == "foo QUX baz"
    assert "ok" in out.lower()


def test_edit_errors_when_not_unique(tmp_path):
    ctx = ToolContext(cwd=tmp_path)
    (tmp_path / "c.txt").write_text("x x")
    out = reg_map(["edit"])["edit"].run({"path": "c.txt", "old": "x", "new": "y"}, ctx)
    assert "error" in out.lower()  # ambiguous match returned as error string, not raise


def test_bash_runs_in_cwd(tmp_path):
    ctx = ToolContext(cwd=tmp_path)
    (tmp_path / "marker").write_text("")
    out = reg_map(["bash"])["bash"].run({"cmd": "ls"}, ctx)
    assert "marker" in out


def test_bash_reports_nonzero_exit(tmp_path):
    out = reg_map(["bash"])["bash"].run({"cmd": "exit 3"}, ToolContext(cwd=tmp_path))
    assert "exit code 3" in out.lower()


def test_search_finds_text(tmp_path):
    (tmp_path / "f.py").write_text("def needle():\n    pass\n")
    out = reg_map(["search"])["search"].run({"query": "needle"}, ToolContext(cwd=tmp_path))
    assert "f.py" in out


def test_unknown_tool_raises():
    with pytest.raises(KeyError):
        build_registry(["read", "nonsense"])


def test_schema_shape():
    t = reg_map(["read"])["read"]
    assert t.schema["type"] == "function"
    assert t.schema["function"]["name"] == "read"
    assert "parameters" in t.schema["function"]


def test_bash_timeout_returns_feedback_instead_of_raising(tmp_path):
    # A hung command must come back as a string the loop can plan against —
    # an escaping TimeoutExpired would kill the whole run.
    out = reg_map(["bash"])["bash"].run(
        {"cmd": "sleep 5", "timeout": 1}, ToolContext(cwd=tmp_path))
    assert "timed out" in out.lower()
    assert "1s" in out


def test_bash_timeout_is_exposed_in_schema():
    # args.get("timeout") is dead unless the model can actually pass it
    props = reg_map(["bash"])["bash"].schema["function"]["parameters"]["properties"]
    assert "timeout" in props
    assert props["timeout"]["type"] == "number"


def test_bash_timeout_is_clamped(tmp_path):
    from setpoint.tools.local import _BASH_TIMEOUT, _BASH_TIMEOUT_MAX, _bash_timeout

    assert _bash_timeout({"timeout": 99999}) == _BASH_TIMEOUT_MAX
    assert _bash_timeout({"timeout": 0}) == _BASH_TIMEOUT      # falsy -> default
    assert _bash_timeout({"timeout": "junk"}) == _BASH_TIMEOUT
    assert _bash_timeout({}) == _BASH_TIMEOUT


def test_bash_missing_cmd_returns_error_not_raise(tmp_path):
    out = reg_map(["bash"])["bash"].run({}, ToolContext(cwd=tmp_path))
    assert "error" in out.lower()


def test_bash_output_is_clipped(tmp_path):
    from setpoint.tools.local import _OUT_MAX

    out = reg_map(["bash"])["bash"].run(
        {"cmd": "printf 'x%.0s' $(seq 1 50000)"}, ToolContext(cwd=tmp_path))
    assert len(out) < _OUT_MAX + 200  # budget plus the elision marker
    assert "truncated" in out


def test_bash_clip_keeps_the_tail_where_failures_print(tmp_path):
    out = reg_map(["bash"])["bash"].run(
        {"cmd": "printf 'x%.0s' $(seq 1 50000); echo FAILED_HERE"},
        ToolContext(cwd=tmp_path))
    assert "FAILED_HERE" in out


def test_read_clips_large_files(tmp_path):
    from setpoint.tools.local import _READ_MAX

    (tmp_path / "big.txt").write_text("y" * 100_000)
    out = reg_map(["read"])["read"].run({"path": "big.txt"}, ToolContext(cwd=tmp_path))
    assert len(out) < _READ_MAX + 200
    assert "truncated" in out


def test_read_leaves_small_files_untouched(tmp_path):
    (tmp_path / "s.txt").write_text("hello")
    assert reg_map(["read"])["read"].run(
        {"path": "s.txt"}, ToolContext(cwd=tmp_path)) == "hello"

import pytest
from loom.tools import build_registry, ToolContext


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

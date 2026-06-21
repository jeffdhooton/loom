from loom.tools import build_registry, ToolContext
import loom.tools.external as ext


def reg_map(names):
    return {t.name: t for t in build_registry(names)}


def test_web_uses_runner(tmp_path, monkeypatch):
    calls = {}

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        class R:
            returncode = 0
            stdout = "# Page\nbody"
            stderr = ""
        return R()

    monkeypatch.setattr(ext.subprocess, "run", fake_run)
    out = reg_map(["web"])["web"].run({"url": "https://x.com"}, ToolContext(cwd=tmp_path))
    assert "body" in out
    assert "trawl" in calls["cmd"][0]


def test_web_graceful_when_missing(tmp_path, monkeypatch):
    def boom(cmd, **kw):
        raise FileNotFoundError("trawl")
    monkeypatch.setattr(ext.subprocess, "run", boom)
    out = reg_map(["web"])["web"].run({"url": "https://x.com"}, ToolContext(cwd=tmp_path))
    assert "unavailable" in out.lower()


def test_scry_graceful_when_missing(tmp_path, monkeypatch):
    def boom(cmd, **kw):
        raise FileNotFoundError("scry")
    monkeypatch.setattr(ext.subprocess, "run", boom)
    out = reg_map(["scry"])["scry"].run({"query": "Foo::bar"}, ToolContext(cwd=tmp_path))
    assert "unavailable" in out.lower()


def test_web_requires_target(tmp_path):
    out = reg_map(["web"])["web"].run({}, ToolContext(cwd=tmp_path))
    assert "required" in out.lower()

from __future__ import annotations

import threading
from pathlib import Path

from types import SimpleNamespace


def _make_fleet(tmp_path, n=4, concurrency=2):
    names = []
    members = []
    for i in range(n):
        sp = tmp_path / f"m{i}.loom.yaml"
        sp.write_text(f"name: m{i}\n")
        names.append(f"m{i}")
        members.append(sp.name)
    fp = tmp_path / "fleet.yaml"
    fp.write_text(f"name: f\nconcurrency: {concurrency}\nmembers:\n"
                  + "".join(f"  - {m}\n" for m in members))
    return fp, names


def test_run_fleet_runs_all_members(tmp_path, monkeypatch):
    from loom import fleet
    monkeypatch.setattr(fleet, "_runs_root", lambda: tmp_path / "runs")
    monkeypatch.setattr("loom.spec.load_spec",
                        lambda p: SimpleNamespace(name=Path(p).stem.replace(".loom", "")))

    def fake_run_loop(spec, *, fresh=False, ui=None, abort_check=None):
        return SimpleNamespace(status="passed")

    fp, names = _make_fleet(tmp_path, n=3, concurrency=2)
    result = fleet.run_fleet(str(fp), run_loop=fake_run_loop)
    assert set(result) == set(names)
    assert all(v == "passed" for v in result.values())


def test_run_fleet_honors_concurrency(tmp_path, monkeypatch):
    from loom import fleet
    monkeypatch.setattr(fleet, "_runs_root", lambda: tmp_path / "runs")
    monkeypatch.setattr("loom.spec.load_spec",
                        lambda p: SimpleNamespace(name=Path(p).stem.replace(".loom", "")))

    lock = threading.Lock()
    state = {"cur": 0, "max": 0}
    release = threading.Event()

    def fake_run_loop(spec, *, fresh=False, ui=None, abort_check=None):
        with lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
        release.wait(timeout=5)
        with lock:
            state["cur"] -= 1
        return SimpleNamespace(status="passed")

    fp, _ = _make_fleet(tmp_path, n=6, concurrency=2)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as ex:
        fut = ex.submit(fleet.run_fleet, str(fp), run_loop=fake_run_loop)
        # give workers time to saturate, then release
        import time
        for _ in range(50):
            if state["max"] >= 2:
                break
            time.sleep(0.01)
        release.set()
        fut.result(timeout=10)
    assert state["max"] <= 2  # never exceeded the concurrency cap


def test_run_fleet_stop_sentinel_skips_unstarted(tmp_path, monkeypatch):
    from loom import fleet
    monkeypatch.setattr(fleet, "_runs_root", lambda: tmp_path / "runs")
    monkeypatch.setattr("loom.spec.load_spec",
                        lambda p: SimpleNamespace(name=Path(p).stem.replace(".loom", "")))
    (tmp_path / "runs").mkdir(parents=True)
    # Pre-create the sentinel; run_fleet clears it at start, so create it via a
    # run_loop that re-touches it after the first member.
    calls = {"n": 0}

    def fake_run_loop(spec, *, fresh=False, ui=None, abort_check=None):
        calls["n"] += 1
        fleet.stop_sentinel_path().parent.mkdir(parents=True, exist_ok=True)
        fleet.stop_sentinel_path().write_text("stop")  # trip it after first member
        return SimpleNamespace(status="passed")

    fp, names = _make_fleet(tmp_path, n=4, concurrency=1)
    result = fleet.run_fleet(str(fp), run_loop=fake_run_loop)
    assert any(v == "skipped" for v in result.values())
    assert calls["n"] < len(names)  # not all members ran


def test_fleet_status_renders_from_state(tmp_path, monkeypatch):
    import json
    from loom import fleet
    runs = tmp_path / "runs"
    monkeypatch.setattr(fleet, "_runs_root", lambda: runs)
    monkeypatch.setattr("loom.spec.load_spec",
                        lambda p: SimpleNamespace(name=Path(p).stem.replace(".loom", "")))
    (runs / "m0").mkdir(parents=True)
    (runs / "m0" / "state.json").write_text(json.dumps(
        {"name": "m0", "status": "passed", "iters": [{"n": 1}], "spent_usd": 0.0}))
    fp, _ = _make_fleet(tmp_path, n=2, concurrency=2)  # m0 ran, m1 pending
    out = fleet.fleet_status(str(fp))
    assert "m0" in out and "passed" in out
    assert "m1" in out and "pending" in out
    assert (tmp_path / "runs").parent.joinpath("fleets", "f", "status.md").exists()


def test_fleet_keys_by_spec_name_not_filename_stem(tmp_path, monkeypatch):
    """Regression: a member file's stem can differ from its spec's declared
    `name:` (e.g. the scribe fleet names files by task but sets name: CS-###).
    Both fleet_status and run_fleet must key/lookup by the spec name."""
    import json
    from loom import fleet
    runs = tmp_path / "runs"
    monkeypatch.setattr(fleet, "_runs_root", lambda: runs)

    def fake_load_spec(p):
        if Path(p).name == "task-a.loom.yaml":
            return SimpleNamespace(name="CS-100")
        return SimpleNamespace(name=Path(p).stem)

    monkeypatch.setattr("loom.spec.load_spec", fake_load_spec)

    # The run directory is keyed by the spec name, not the filename stem.
    (runs / "CS-100").mkdir(parents=True)
    (runs / "CS-100" / "state.json").write_text(json.dumps(
        {"name": "CS-100", "status": "passed", "iters": [], "spent_usd": 0.0}))

    member = tmp_path / "task-a.loom.yaml"
    member.write_text("name: CS-100\n")
    fp = tmp_path / "fleet.yaml"
    fp.write_text("name: f\nconcurrency: 1\nmembers:\n  - task-a.loom.yaml\n")

    out = fleet.fleet_status(str(fp))
    status_line = next(l for l in out.splitlines() if l.startswith("CS-100"))
    assert "passed" in status_line
    assert "pending" not in status_line

    def fake_run_loop(spec, *, fresh=False, ui=None, abort_check=None):
        return SimpleNamespace(status="passed")

    result = fleet.run_fleet(str(fp), run_loop=fake_run_loop)
    assert result == {"CS-100": "passed"}

from __future__ import annotations

import concurrent.futures
import threading
from pathlib import Path

from loom.__main__ import _runs_root, run_loop as _default_run_loop
from loom.fleet_spec import load_fleet
from loom.ui import NullUI


def stop_sentinel_path() -> Path:
    return _runs_root().parent / "STOP"


def _member_name(member_path: Path) -> str:
    # Fallback when the spec can't be loaded: member paths look like
    # ".../<name>.loom.yaml"; strip both suffixes.
    return member_path.stem.replace(".loom", "")


def _run_name(member_path: Path) -> str:
    """Resolve the run-lookup key for a member: the spec's declared `name:`
    field (that's what `Memory` keys `~/.loom/runs/<name>/` by), falling
    back to the filename stem if the spec can't be loaded."""
    from loom.spec import load_spec

    try:
        return load_spec(str(member_path)).name
    except Exception:
        return _member_name(member_path)


def _run_member(member_path: Path, fresh: bool, run_loop) -> tuple[str, str]:
    from loom.spec import load_spec

    sentinel = stop_sentinel_path()
    try:
        spec = load_spec(str(member_path))
    except Exception:
        return _member_name(member_path), "error"
    try:
        state = run_loop(spec, fresh=fresh, ui=NullUI(),
                          abort_check=lambda: sentinel.exists())
        return spec.name, getattr(state, "status", "error")
    except Exception:
        return spec.name, "error"


def run_fleet(fleet_path: str, *, fresh: bool = False, run_loop=None) -> dict[str, str]:
    """Run every member of a fleet spec in a bounded thread pool.

    Each member is fully isolated (its own worktree via `prepare_workspace`),
    so threads are safe here even though agent turns are subprocesses.

    STOP semantics: a stale sentinel from a previous run is cleared at the
    start of every `run_fleet` call. If a member's run_loop (or an external
    actor) re-creates the sentinel while the fleet is in flight, in-progress
    members keep running until their own `abort_check` trips (they exit at
    the next iteration boundary, bounded by max_iters/wall_clock_secs) but
    no *new* member is submitted -- it is recorded as "skipped" instead.
    """
    run_loop = run_loop or _default_run_loop
    fs = load_fleet(fleet_path)
    sentinel = stop_sentinel_path()
    if sentinel.exists():
        sentinel.unlink()  # clear a stale sentinel so a fresh fleet is not blocked

    results: dict[str, str] = {}
    skipped = 0

    # ThreadPoolExecutor.submit() enqueues work immediately regardless of
    # worker availability -- it does not block until a slot is actually
    # free. If members were submitted in a tight, unthrottled loop, the
    # STOP check ahead of member N+1 would race against member N's
    # *execution* (thread start + run_loop) rather than reflecting
    # completed work, which would make the "skip unstarted members"
    # behavior nondeterministic. A semaphore sized to `concurrency` gives
    # real backpressure: the next member is only considered for
    # submission once an in-flight slot has genuinely been released by a
    # completed run_loop call, so the STOP check is meaningful.
    sem = threading.Semaphore(fs.concurrency)

    with concurrent.futures.ThreadPoolExecutor(max_workers=fs.concurrency) as ex:
        futures: list[concurrent.futures.Future] = []

        def wrapped(member_path: Path) -> tuple[str, str]:
            try:
                return _run_member(member_path, fresh, run_loop)
            finally:
                sem.release()

        for member in fs.members:
            sem.acquire()
            if sentinel.exists():
                sem.release()
                results[_run_name(member)] = "skipped"
                skipped += 1
                continue
            futures.append(ex.submit(wrapped, member))

        for fut in concurrent.futures.as_completed(futures):
            name, status = fut.result()
            results[name] = status

    if skipped:
        print(f"loom fleet: STOP sentinel detected — skipped {skipped} unstarted member(s)")

    return results


def fleet_status(fleet_path: str) -> str:
    import json
    fs = load_fleet(fleet_path)
    runs_root = _runs_root()
    lines = [f"# fleet {fs.name}", "", f"{'member':30} {'status':16} {'iters':>6} {'spend':>8}"]
    for member in fs.members:
        name = _run_name(member)
        sp = runs_root / name / "state.json"
        if sp.exists():
            s = json.loads(sp.read_text())
            lines.append(f"{name:30} {s.get('status','?'):16} "
                         f"{len(s.get('iters', [])):>6} ${s.get('spent_usd', 0):>7.2f}")
        else:
            lines.append(f"{name:30} {'pending':16} {0:>6} ${0:>7.2f}")
    text = "\n".join(lines) + "\n"
    out_dir = runs_root.parent / "fleets" / fs.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "status.md").write_text(text)
    return text

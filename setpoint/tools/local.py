from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from setpoint.clip import clip
from . import Tool, ToolContext, _fn

# Tool output is re-sent on every subsequent turn, so an unbounded result does
# not cost one window — it costs one per remaining turn. Files get a larger
# budget than command output because reading source is how the model builds
# context in the first place.
_READ_MAX = 12000
_OUT_MAX = 6000

_BASH_TIMEOUT = 300.0
_BASH_TIMEOUT_MAX = 600.0
_REAP_TIMEOUT = 10.0  # bounded second wait after killpg, so a leaked child can't hang us


def _resolve(ctx: ToolContext, path: str) -> Path:
    return (ctx.cwd / path).resolve()


def _read(args: dict, ctx: ToolContext) -> str:
    try:
        return clip(_resolve(ctx, args["path"]).read_text(), _READ_MAX)
    except Exception as e:  # surface as string; the model reads errors as feedback
        return f"ERROR reading {args.get('path')}: {e}"


def _write(args: dict, ctx: ToolContext) -> str:
    try:
        p = _resolve(ctx, args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"])
        return f"ok: wrote {len(args['content'])} chars to {args['path']}"
    except Exception as e:
        return f"ERROR writing {args.get('path')}: {e}"


def _edit(args: dict, ctx: ToolContext) -> str:
    try:
        p = _resolve(ctx, args["path"])
        text = p.read_text()
        count = text.count(args["old"])
        if count == 0:
            return f"ERROR: old string not found in {args['path']}"
        if count > 1:
            return f"ERROR: old string is ambiguous ({count} matches) in {args['path']}"
        p.write_text(text.replace(args["old"], args["new"], 1))
        return f"ok: edited {args['path']}"
    except Exception as e:
        return f"ERROR editing {args.get('path')}: {e}"


def _bash_timeout(args: dict) -> float:
    try:
        requested = float(args.get("timeout") or _BASH_TIMEOUT)
    except (TypeError, ValueError):
        return _BASH_TIMEOUT
    return max(1.0, min(requested, _BASH_TIMEOUT_MAX))


def _bash(args: dict, ctx: ToolContext) -> str:
    """Run a shell command. Never raises and never blocks past the timeout —
    a tool that escapes with an exception kills the iteration instead of
    handing the loop feedback it could act on."""
    timeout = _bash_timeout(args)
    try:
        # start_new_session + killpg: a leaked background child would otherwise
        # hold the output pipe open and block the read past the shell's exit.
        proc = subprocess.Popen(
            args["cmd"], shell=True, cwd=ctx.cwd, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception as e:
        return f"ERROR launching command: {e}"

    timed_out = False
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                stdout, stderr = proc.communicate(timeout=_REAP_TIMEOUT)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""  # orphan still holds the pipe; give up on output
    except Exception as e:
        return f"ERROR running command: {e}"

    out = clip(((stdout or "") + (stderr or "")).strip(), _OUT_MAX)
    if timed_out:
        msg = (f"ERROR: command timed out after {timeout:g}s and was killed "
               "(hung, or left a background process holding its output pipe)")
        return f"{msg}\npartial output:\n{out}" if out else msg
    if proc.returncode != 0:
        out += f"\n[exit code {proc.returncode}]"
    return out.strip() or "[no output]"


def _search(args: dict, ctx: ToolContext) -> str:
    # ripgrep if available, else python fallback
    try:
        proc = subprocess.run(
            ["rg", "-n", "--max-count", "50", args["query"]],
            cwd=ctx.cwd, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode in (0, 1):
            return clip(proc.stdout.strip(), _OUT_MAX) or "[no matches]"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    hits = []
    for f in Path(ctx.cwd).rglob("*"):
        if f.is_file():
            try:
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    if args["query"] in line:
                        hits.append(f"{f.relative_to(ctx.cwd)}:{i}:{line}")
            except (UnicodeDecodeError, OSError):
                continue
    return clip("\n".join(hits[:50]), _OUT_MAX) or "[no matches]"


TOOLS = [
    Tool("read", _fn("read", "Read a file relative to the workspace.",
                     {"path": {"type": "string"}}, ["path"]), _read),
    Tool("write", _fn("write", "Write (overwrite) a file with content.",
                      {"path": {"type": "string"}, "content": {"type": "string"}},
                      ["path", "content"]), _write),
    Tool("edit", _fn("edit", "Replace a unique substring in a file.",
                     {"path": {"type": "string"}, "old": {"type": "string"},
                      "new": {"type": "string"}}, ["path", "old", "new"]), _edit),
    Tool("bash", _fn("bash", "Run a shell command in the workspace and return output.",
                     {"cmd": {"type": "string"},
                      "timeout": {"type": "number",
                                  "description": f"Seconds before the command is killed "
                                                 f"(default {_BASH_TIMEOUT:g}, "
                                                 f"max {_BASH_TIMEOUT_MAX:g})."}},
                     ["cmd"]), _bash),
    Tool("search", _fn("search", "Search workspace file contents for a string.",
                       {"query": {"type": "string"}}, ["query"]), _search),
]

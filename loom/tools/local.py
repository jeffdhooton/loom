from __future__ import annotations

import subprocess
from pathlib import Path

from . import Tool, ToolContext, _fn


def _resolve(ctx: ToolContext, path: str) -> Path:
    return (ctx.cwd / path).resolve()


def _read(args: dict, ctx: ToolContext) -> str:
    try:
        return _resolve(ctx, args["path"]).read_text()
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


def _bash(args: dict, ctx: ToolContext) -> str:
    proc = subprocess.run(
        args["cmd"], shell=True, cwd=ctx.cwd,
        capture_output=True, text=True, timeout=args.get("timeout", 300),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
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
            return proc.stdout.strip() or "[no matches]"
    except FileNotFoundError:
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
    return "\n".join(hits[:50]) or "[no matches]"


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
                     {"cmd": {"type": "string"}}, ["cmd"]), _bash),
    Tool("search", _fn("search", "Search workspace file contents for a string.",
                       {"query": {"type": "string"}}, ["query"]), _search),
]

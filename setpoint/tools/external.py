from __future__ import annotations

import subprocess

from . import Tool, ToolContext, _fn


def _scry(args: dict, ctx: ToolContext) -> str:
    try:
        proc = subprocess.run(
            ["scry", "refs", args["query"]],
            cwd=ctx.cwd, capture_output=True, text=True, timeout=30,
        )
        return (proc.stdout or proc.stderr or "[no results]").strip()
    except FileNotFoundError:
        return "[scry unavailable: binary not on PATH — use the `search` tool instead]"
    except Exception as e:
        return f"[scry error: {e}]"


def _web(args: dict, ctx: ToolContext) -> str:
    target = args.get("url") or args.get("query")
    if not target:
        return "[web: url or query required]"
    try:
        proc = subprocess.run(
            ["trawl", "scrape", target, "--format", "markdown"],
            capture_output=True, text=True, timeout=120,
        )
        return (proc.stdout or proc.stderr or "[no content]").strip()
    except FileNotFoundError:
        return "[web unavailable: trawl binary not on PATH]"
    except Exception as e:
        return f"[web error: {e}]"


TOOLS = [
    Tool("scry", _fn("scry", "Query the scry code-intelligence daemon for symbol refs.",
                     {"query": {"type": "string"}}, ["query"]), _scry),
    Tool("web", _fn("web", "Fetch a URL (or search) as clean markdown via trawl.",
                    {"url": {"type": "string"}, "query": {"type": "string"}}, []), _web),
]

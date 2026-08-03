from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class ToolContext:
    cwd: Path


@dataclass
class Tool:
    name: str
    schema: dict
    run: Callable[[dict, ToolContext], str]


def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


def build_registry(names: list[str]) -> list[Tool]:
    from . import local, external

    catalog: dict[str, Tool] = {}
    for mod in (local, external):
        for tool in mod.TOOLS:
            catalog[tool.name] = tool
    out = []
    for n in names:
        if n not in catalog:
            raise KeyError(f"unknown tool: {n}")
        out.append(catalog[n])
    return out
